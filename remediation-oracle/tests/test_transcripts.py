"""Parse agent and subagent session logs (Codex CLI) into a list of tool calls with their output."""
import gzip
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import agent_llm  # noqa: E402


def item(payload):
    return json.dumps({"type": "response_item", "payload": payload})


LINES = [
    json.dumps({"type": "session_meta", "payload": {"id": "x"}}),
    item({"type": "function_call", "name": "exec_command", "call_id": "c1", "arguments": '{"cmd": "ls"}'}),
    item({"type": "function_call_output", "call_id": "c1",
          "output": "Chunk ID: 1\nProcess exited with code 2\nOutput:\nls: x: No such file"}),
    item({"type": "custom_tool_call", "name": "apply_patch", "call_id": "c2", "input": "*** Begin Patch"}),
    item({"type": "web_search_call", "action": {"type": "search", "query": "redis eviction"}}),
    "not json",
]


class TranscriptCalls(unittest.TestCase):
    def check(self, path):
        calls = agent_llm.transcript_calls([path])
        self.assertEqual([c["name"] for c in calls], ["exec_command", "apply_patch", "web_search"])
        self.assertEqual(calls[0]["exit_code"], 2)
        self.assertIn("No such file", calls[0]["output"])
        self.assertNotIn("exit_code", calls[1])
        self.assertIn("redis eviction", calls[2]["args"])

    def test_plain_and_gzip_transcripts(self):
        with tempfile.TemporaryDirectory() as d:
            plain = os.path.join(d, "rollout-2026-11-07-01a1b19d-614b-7243-b4ab-f9199fa9cdea.jsonl")
            with open(plain, "w") as f:
                f.write("\n".join(LINES) + "\n")
            self.check(plain)
            with open(plain, "rb") as fi, gzip.open(plain + ".gz", "wb") as fo:
                fo.write(fi.read())
            self.check(plain + ".gz")
            self.assertEqual(agent_llm.transcript_calls([plain + ".gz"])[0]["thread"], "f9199fa9cdea")


if __name__ == "__main__":
    unittest.main()
