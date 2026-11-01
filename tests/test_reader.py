"""Unit tests for meetily_reader and textnorm (standard library only).

  python3 -m unittest discover -s tests
"""
import json, sqlite3, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "eval"))
import meetily_reader as mr  # noqa: E402
from textnorm import normalise, wer  # noqa: E402

SEGS = [
    {"text": "We use RingCentral for the phones. The dispatcher creates a job in ServiceTitan.", "start": 0.0, "end": 8.0, "speaker": None},
    {"text": "After six the calls roll over to an answering service. We lost about eight jobs a week.", "start": 8.0, "end": 16.0, "speaker": None},
]


class ReaderTests(unittest.TestCase):
    def test_supported_item_gets_quote(self):
        ev = mr.link_quote("Calls roll over to an answering service after six", SEGS)
        self.assertIsNotNone(ev)
        self.assertIn("answering service", ev["quote"])
        self.assertEqual(ev["t"], "00:08")

    def test_invented_item_is_flagged(self):
        self.assertIsNone(mr.link_quote("Uses Salesforce and HubSpot for marketing automation", SEGS))

    def test_parse_sections_tables_and_bullets(self):
        md = "**Workflow Steps**\n\n| **Step** | **Who** | **Tool** |\n| --- | --- | --- |\n| Create job | Dispatcher | ServiceTitan |\n\n**Tools and Systems**\n\n*   RingCentral\n"
        s = mr.parse_sections(md)
        self.assertEqual(s["Workflow Steps"], ["Create job | Dispatcher | ServiceTitan"])
        self.assertEqual(s["Tools and Systems"], ["RingCentral"])

    def test_end_to_end_on_a_fake_db(self):
        tmp = Path(tempfile.mkdtemp())
        db = tmp / "meeting_minutes.sqlite"
        con = sqlite3.connect(db)
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
        con.commit(); con.close()
        c = mr.open_copy(db)
        m = mr.find_meeting(c, "m1")
        x = mr.build(m, mr.segments(c, "m1"), mr.summary_markdown(c, "m1")[0])
        self.assertEqual(x["stats"]["items"], 1)
        self.assertEqual(x["stats"]["items_with_quote"], 1)
        self.assertEqual(len(x["candidate_agent_tasks"]), 0)  # no repetitive-work cue in this pain


class NormTests(unittest.TestCase):
    def test_numbers_and_brands(self):
        self.assertEqual(normalise("About 120 leads in Job Nimbus"), normalise("about a hundred and twenty leads in JobNimbus"))

    def test_wer_counts(self):
        r = wer("a b c d".split(), "a x c d e".split())
        self.assertEqual((r["sub"], r["del"], r["ins"]), (1, 0, 1))


if __name__ == "__main__":
    unittest.main()
