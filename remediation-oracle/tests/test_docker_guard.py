"""Decision functions of the Docker proxy (docker_guard) and isolation v4 in agent_llm. The cases that really run through
Docker and sandbox-exec are in check_isolation.py; here only the pure logic is tested, without Docker."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import agent_llm  # noqa: E402
import docker_guard as G  # noqa: E402


class Route(unittest.TestCase):
    def test_checked_endpoints(self):
        self.assertEqual(G.route("POST", "/v1.47/containers/create"), ("create", None))
        self.assertEqual(G.route("POST", "/containers/create"), ("create", None))
        self.assertEqual(G.route("POST", "/v1.47/containers/abc_1/start"), ("start", "abc_1"))
        self.assertEqual(G.route("POST", "/v1.47/containers/abc/restart"), ("start", "abc"))
        self.assertEqual(G.route("POST", "/v1.47/containers/abc/exec"), ("exec", "abc"))
        self.assertEqual(G.route("POST", "/v1.47/volumes/create"), ("volume", None))
        self.assertEqual(G.route("GET", "/v1.47/containers/json"), (None, None))

    def test_denied_and_ambiguous_paths(self):
        self.assertEqual(G.route("POST", "/v1.47/swarm/init")[0], "deny")
        self.assertEqual(G.route("GET", "/v1.47/secrets")[0], "deny")
        for p in ("/v1.47/containers%2Fcreate", "/v1.47//containers/create", "/v1.47/x/../containers/create",
                  "/v1.47/containers/x/..", "containers/create"):
            self.assertEqual(G.route("POST", p)[0], "bad", p)


class CheckCreate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self.tmp.name)
        os.mkdir(os.path.join(self.root, "src"))

    def tearDown(self):
        self.tmp.cleanup()

    def denied(self, hc):
        with self.assertRaises(G.Denied):
            G.check_create({"HostConfig": hc}, self.root)

    def test_binds(self):
        G.check_create({"HostConfig": {"Binds": [self.root + "/src:/x", "data:/d"]}}, self.root)
        self.denied({"Binds": [os.path.expanduser("~") + ":/h"]})
        self.denied({"Binds": [self.root + "/../:/x"]})
        self.denied({"Binds": ["../x:/x"]})

    def test_mounts(self):
        G.check_create({"HostConfig": {"Mounts": [{"Type": "bind", "Source": self.root + "/src"},
                                                  {"Type": "tmpfs", "Target": "/t"}, {"Target": "/v"}]}}, self.root)
        self.denied({"Mounts": [{"Type": "bind", "Source": "/"}]})
        self.denied({"Mounts": [{"Type": "volume", "VolumeOptions": {"DriverConfig": {"Options": {"device": "/Users"}}}}]})
        self.denied({"Mounts": [{"Type": "npipe", "Source": "x"}]})

    def test_privilege(self):
        for hc in ({"Privileged": True}, {"PidMode": "host"}, {"IpcMode": "HOST"}, {"UsernsMode": "host"},
                   {"CapAdd": ["cap_sys_admin"]}, {"CapAdd": ["ALL"]}, {"Devices": [{"PathOnHost": "/dev/fuse"}]},
                   {"DeviceCgroupRules": ["c *:* rwm"]}, {"VolumesFrom": ["other"]},
                   {"SecurityOpt": ["seccomp=unconfined"]}, {"SecurityOpt": ["label=disable"]}):
            self.denied(hc)
        G.check_create({"HostConfig": {"CapAdd": ["NET_ADMIN"]}}, self.root)

    def test_keys_are_case_insensitive_and_unique(self):
        with self.assertRaises(G.Denied):
            G.check_create({"hostconfig": {"binds": ["/:/h"]}}, self.root)
        with self.assertRaises(G.Denied):
            G.check_create({"HostConfig": {"Binds": []}, "hostConfig": {"Binds": ["/:/h"]}}, self.root)

    def test_symlink_inside_workspace_pointing_out(self):
        link = os.path.join(self.root, "out")
        os.symlink(os.path.expanduser("~"), link)
        self.denied({"Binds": [link + ":/h"]})
        with self.assertRaises(G.Denied):
            G.check_started({"Mounts": [{"Type": "bind", "Source": link}]}, self.root)
        G.check_started({"Mounts": [{"Type": "bind", "Source": self.root + "/src"}]}, self.root)

    def test_exec_and_volume(self):
        with self.assertRaises(G.Denied):
            G.check_body("exec", {"Privileged": True}, self.root)
        with self.assertRaises(G.Denied):
            G.check_body("volume", {"DriverOpts": {"device": "/Users"}}, self.root)
        G.check_body("volume", {"DriverOpts": {"device": self.root + "/src"}}, self.root)


class AccessKind(unittest.TestCase):
    def test_proxy_refusal_is_blocked(self):
        out = "docker: Error response from daemon: mounting host path /Users/user " + G.DENY_MSG
        c = {"command": "docker run --rm -v /Users/user:/h alpine cat /h/srv/acme-payments/x", "output": out}
        self.assertEqual(agent_llm.access_kind(c), "blocked")
        self.assertEqual(agent_llm.peek_flags([c]), [])

    def test_second_docker_call_still_counts(self):
        c = {"command": "docker run -v /Users/user:/h alpine true; docker exec x cat /srv/acme-payments/y",
             "output": G.DENY_MSG}
        self.assertEqual(agent_llm.access_kind(c), "docker")


@unittest.skipIf(agent_llm.ISOLATION_V4, "checked only when isolation v4 is off")
class V3Unchanged(unittest.TestCase):
    def test_off_means_v3(self):
        self.assertEqual(agent_llm.sandbox_profile(), agent_llm.SANDBOX_PROFILE)
        self.assertEqual(agent_llm.agent_env(), {**os.environ, "CODEX_HOME": str(agent_llm.AGENT_HOME)})


if __name__ == "__main__":
    unittest.main()
