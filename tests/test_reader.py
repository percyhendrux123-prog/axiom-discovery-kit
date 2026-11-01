"""Unit tests for meetily_reader, score.check_items and textnorm (standard library only).

  python3 -m unittest discover -s tests
"""
import json, sqlite3, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "eval"))
import meetily_reader as mr  # noqa: E402
from textnorm import normalise, wer  # noqa: E402
from score import check_items  # noqa: E402

SEGS = [
    {"text": "We use RingCentral for the phones. The dispatcher creates a job in ServiceTitan.", "start": 0.0, "end": 8.0, "speaker": None},
    {"text": "After six the calls roll over to an answering service. We lost about eight jobs a week.", "start": 8.0, "end": 16.0, "speaker": None},
]
QA = [
    {"text": "And how many estimates go out each month?", "start": 0.0, "end": 3.0, "speaker": None},
    {"text": "About forty five estimates a month.", "start": 3.0, "end": 6.0, "speaker": None},
]


def fake_meetily_db(path: Path, wal: bool = False):
    con = sqlite3.connect(path)
    if wal:
        con.execute("pragma journal_mode=wal")
    con.executescript("""
      create table meetings (id text primary key, title text, created_at text, updated_at text, folder_path text);
      create table transcripts (id text primary key, meeting_id text, transcript text, timestamp text, summary text,
        action_items text, key_points text, audio_start_time real, audio_end_time real, duration real, speaker text);
      create table summary_processes (meeting_id text primary key, status text, created_at text, updated_at text,
        error text, result text, start_time text, end_time text, chunk_count int, processing_time real, metadata text,
        result_backup text, result_backup_timestamp text);
    """)
    con.execute("insert into meetings values ('m1','Test call','2026-11-01T00:00:00','2026-11-01T00:00:00',null)")
    for i, s in enumerate(SEGS):
        con.execute("insert into transcripts (id, meeting_id, transcript, timestamp, audio_start_time, audio_end_time) values (?,?,?,?,?,?)",
                    (f"t{i}", "m1", s["text"], "x", s["start"], s["end"]))
    md = "**Pain Points**\n\n| Pain | Cost or impact |\n| --- | --- |\n| Calls roll over to an answering service after six | about eight jobs lost a week |\n"
    con.execute("insert into summary_processes (meeting_id, status, created_at, updated_at, result) values ('m1','completed','x','x',?)",
                (json.dumps({"markdown": md}),))
    con.commit()
    return con


class SnapshotTests(unittest.TestCase):
    def test_end_to_end_on_a_closed_db(self):
        db = Path(tempfile.mkdtemp()) / "meeting_minutes.sqlite"
        fake_meetily_db(db, wal=True).close()  # closed WAL database: no -wal / -shm left
        c = mr.open_copy(db)
        m = mr.find_meeting(c, "m1")
        x = mr.build(m, mr.segments(c, "m1"), mr.summary_markdown(c, "m1")[0])
        self.assertEqual(x["stats"]["items"], 1)
        self.assertEqual(x["stats"]["items_with_candidate_quote"], 1)
        self.assertEqual(len(x["candidate_agent_tasks"]), 0)  # no repetitive-work cue in this pain

    def test_snapshot_is_read_only_and_source_untouched(self):
        db = Path(tempfile.mkdtemp()) / "meeting_minutes.sqlite"
        fake_meetily_db(db).close()
        before = db.read_bytes()
        c = mr.open_copy(db)
        with self.assertRaises(sqlite3.OperationalError):
            c.execute("insert into meetings (id) values ('x')")
        self.assertEqual(db.read_bytes(), before)

    def test_live_wal_snapshot_is_coherent_under_a_concurrent_writer(self):
        """Reviewer's race: a writer creates table y, checkpoints, then sets x=2 in the WAL while the
        reader is copying. The snapshot must never show x=2 without y."""
        db = Path(tempfile.mkdtemp()) / "meeting_minutes.sqlite"
        w = fake_meetily_db(db, wal=True)  # writer stays open, like the running app
        w.execute("create table x (v int)"); w.execute("insert into x values (1)"); w.commit()
        for i in range(200):  # enough pages that the backup takes several steps
            w.execute("insert into transcripts (id, meeting_id, transcript) values (?, 'm1', ?)", (f"pad{i}", "x" * 500))
        w.commit()
        fired = []

        def writer_mid_copy(status, remaining, total):
            if not fired:
                fired.append(1)
                w.execute("create table y (v int)"); w.commit()
                w.execute("pragma wal_checkpoint(truncate)")
                w.execute("update x set v = 2"); w.commit()

        c = mr.open_copy(db, pages=1, progress=writer_mid_copy)
        self.assertTrue(fired)
        v = c.execute("select v from x").fetchone()[0]
        has_y = c.execute("select count(*) from sqlite_master where name = 'y'").fetchone()[0] == 1
        self.assertIn((v, has_y), {(1, False), (2, True)})
        w.close()


class QuoteTests(unittest.TestCase):
    def test_supported_item_gets_candidate_quote(self):
        ev = mr.link_quote("Calls roll over to an answering service after six", SEGS)
        self.assertEqual(ev["status"], "candidate")
        self.assertIn("answering service", ev["quote"])
        self.assertEqual(ev["t"], "00:08")

    def test_invented_item_is_flagged(self):
        self.assertIsNone(mr.link_quote("Uses Salesforce and HubSpot for marketing automation", SEGS))

    def test_question_is_not_evidence(self):
        ev = mr.link_quote("Estimates sent per month: ~45", QA)
        self.assertEqual(ev["status"], "candidate")
        self.assertFalse(ev["quote"].endswith("?"))
        self.assertIn("forty five", ev["quote"])
        self.assertIsNone(mr.link_quote("Estimates sent per month", QA[:1]))  # question only: no quote

    def test_wrong_number_is_flagged(self):
        ev = mr.link_quote("Estimates sent per month: 450", QA)
        self.assertEqual(ev["status"], "numbers_missing")
        self.assertIn("hundred", ev["numbers_missing"])

    def test_number_in_a_later_cell_is_checked(self):
        ev = mr.link_quote("Calls roll over to an answering service after six | about twelve jobs lost a week", SEGS)
        self.assertEqual(ev["status"], "numbers_missing")
        self.assertEqual(ev["numbers_missing"], ["twelve"])

    def test_parse_sections_tables_and_bullets(self):
        md = "**Workflow Steps**\n\n| **Step** | **Who** | **Tool** |\n| --- | --- | --- |\n| Create job | Dispatcher | ServiceTitan |\n\n**Tools and Systems**\n\n*   RingCentral\n"
        s = mr.parse_sections(md)
        self.assertEqual(s["Workflow Steps"], ["Create job | Dispatcher | ServiceTitan"])
        self.assertEqual(s["Tools and Systems"], ["RingCentral"])


class KeywordChecklistTests(unittest.TestCase):
    def hit(self, md, groups):
        return check_items(md, [{"id": "x", "cat": "c", "item": "i", "all": groups}])[0]["captured"]

    def test_whole_words_only(self):
        self.assertFalse(self.hit("Freight jobs are never lost.", [["eight"]]))
        self.assertTrue(self.hit("About 8 jobs lost a week.", [["eight"]]))
        self.assertTrue(self.hit("Dispatchers read the messages.", [["message"]]))

    def test_negation(self):
        self.assertFalse(self.hit("We do not use RingCentral.", [["ringcentral"]]))
        self.assertTrue(self.hit("We use Ring Central for phones.", [["ringcentral"]]))

    def test_groups_must_share_a_line(self):
        self.assertFalse(self.hit("Owner of the company.\nAbout 30 calls a week.", [["owner"], ["week"]]))
        self.assertTrue(self.hit("Owner approvals take up to a week.", [["owner"], ["week"]]))

    def test_explicit_prefix(self):
        self.assertTrue(self.hit("The estimator builds it.", [["estimat*"]]))
        self.assertFalse(self.hit("The estimator builds it.", [["estimat"]]))


class NormTests(unittest.TestCase):
    def test_numbers_and_brands(self):
        self.assertEqual(normalise("About 120 leads in Job Nimbus"), normalise("about a hundred and twenty leads in JobNimbus"))

    def test_email_spelling(self):
        self.assertEqual(normalise("e-mail"), ["email"])

    def test_wer_counts(self):
        r = wer("a b c d".split(), "a x c d e".split())
        self.assertEqual((r["sub"], r["del"], r["ins"]), (1, 0, 1))


if __name__ == "__main__":
    unittest.main()
