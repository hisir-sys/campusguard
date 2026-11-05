"""Phase 6: alert-only synchronisation between independent servers (real API servers + real databases)."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import threading
import time

import pytest

from campusguard.server.api import ApiServer
from campusguard.server.client import RemoteServerClient
from campusguard.server.config import ServerConfig, normalise, normalise_peers
from campusguard.server.sync import (
    PAGE_SIZE, STATE_DISCONNECTED, STATE_ONLINE, STATE_UNAUTHORIZED, STATE_WRONG_SCHOOL,
    PeerSync, SyncFacade, school_id_from_email,
)
from campusguard.settings import CameraConfig
from campusguard.storage import Repository

SCHOOL = "school-test"


class SyncBackend:
    """The sync endpoints exactly as HostBackend serves them, minus cameras/AI."""

    def __init__(self, facade: SyncFacade):
        self.sync = facade

    def sync_identity(self): return self.sync.identity()
    def sync_events(self, since, limit): return self.sync.events(since, limit)
    def sync_overview(self): return self.sync.overview()
    def sync_alerts(self, limit): return self.sync.remote_alerts(limit)
    def status(self): return {"version": "t"}


class Node:
    def __init__(self, tmp_path, name, school=SCHOOL, token=None, port=0):
        self.name = name
        self.token = token or (name[0] * 32)
        self.repo = Repository(database_path=tmp_path / f"{name}.db", footage_dir=tmp_path / f"{name}-footage")
        self.peers: list[dict] = []
        self.tokens: dict[str, str] = {}
        self.facade = SyncFacade(self.repo, f"id-{name}", name, school, "t", lambda: self.peers)
        self.api = ApiServer("127.0.0.1", port, self.token, SyncBackend(self.facade))
        self.api.start()
        self.sync = PeerSync(self.repo, self.facade, lambda: self.peers, lambda a: self.tokens.get(a, ""),
                             poll_seconds=0.05)
        self.new_alerts: list = []
        self.sync._on_new_alert = lambda peer, event: self.new_alerts.append((peer["name"], event["incident_id"]))

    @property
    def address(self): return f"http://127.0.0.1:{self.api.port}"

    def connect(self, other: "Node", token=None):
        self.peers.append({"name": other.name, "address": other.address, "ca_file": ""})
        self.tokens[other.address] = token or other.token

    def fight(self, camera="CAM-024", severity="HIGH", confidence=0.9):
        cam = CameraConfig(camera, f"Camera {camera[-2:]}", "RTSP", "rtsp://x", True, "now")
        return self.repo.create_incident(cam, "Fight detected", confidence, severity, 0)

    def close(self):
        self.sync.stop()
        self.api.stop()


@pytest.fixture
def nodes(tmp_path):
    made = []

    def make(name, **kwargs):
        node = Node(tmp_path, name, **kwargs)
        made.append(node)
        return node

    yield make
    for node in made:
        node.close()


def test_config_identity_and_peer_normalisation():
    config = normalise({"server_id": "abc", "server_name": "Server One", "school_id": "S1",
                        "peers": [{"name": "B", "address": "http://10.0.0.2:8765/"},
                                  {"address": "ftp://bad"}, {"address": "http://10.0.0.2:8765"}, "junk"]})
    assert (config.server_id, config.server_name, config.school_id) == ("abc", "Server One", "S1")
    assert [p["address"] for p in config.peers] == ["http://10.0.0.2:8765"]
    assert normalise_peers("nope") == []
    assert ServerConfig().peers == [] and ServerConfig().peers is not ServerConfig().peers


def test_school_id_is_stable_and_case_insensitive():
    assert school_id_from_email("Admin@School.org ") == school_id_from_email("admin@school.org")
    assert school_id_from_email("a@x.org") != school_id_from_email("b@x.org")


def test_sequence_changes_and_migration_of_existing_rows(tmp_path):
    repo = Repository(database_path=tmp_path / "x.db", footage_dir=tmp_path / "f")
    first = repo.create_incident(CameraConfig("CAM-1", "C1", "RTSP", "r", True, "n"), "Fight", 0.9, "HIGH", 0)
    events, latest = repo.list_sync_events(0)
    assert [e["incident_id"] for e in events] == [first["public_id"]] and latest == events[0]["seq"] == 1
    repo.update_incident_status(first["public_id"], "RESOLVED")
    repo.attach_incident_footage(first["public_id"], str(tmp_path / "clip.mp4"))
    events, latest = repo.list_sync_events(1)
    assert events[0]["status"] == "RESOLVED" and events[0]["has_footage"] and events[0]["seq"] == latest == 3
    assert repo.list_sync_events(latest)[0] == []


def test_fight_on_server_one_appears_on_server_two_with_source_and_camera(nodes):
    one, two = nodes("one"), nodes("two")
    two.connect(one)
    incident = one.fight("CAM-024", "HIGH", 0.93)
    two.sync.sync_once()
    alerts = two.facade.remote_alerts(10)
    assert len(alerts) == 1
    alert = alerts[0]
    assert (alert["source_name"], alert["camera_id"], alert["incident_id"]) == ("one", "CAM-024", incident["public_id"])
    assert alert["source_address"] == one.address and alert["footage_location"] == "source_server"
    assert alert["severity"] == "HIGH" and abs(alert["confidence"] - 0.93) < 1e-9
    assert two.new_alerts == [("one", incident["public_id"])]
    assert two.repo.list_incidents() == []        # remote alerts are never local incidents


def test_school_wide_counts_do_not_double_count(nodes):
    one, two = nodes("one"), nodes("two")
    two.connect(one)
    one.connect(two)
    for _ in range(4):
        one.fight("CAM-%02d" % 1, "HIGH")
        one.repo.update_incident_status(f"INC-{_ + 1:05d}", "RESOLVED")   # frees the camera cooldown
    for i in range(8):
        two.fight("CAM-%02d" % 5, "MEDIUM")
        two.repo.update_incident_status(f"INC-{i + 1:05d}", "RESOLVED")
    for _ in range(5):                    # repeated, overlapping syncs must not inflate anything
        one.sync.sync_once()
        two.sync.sync_once()
    overview = two.facade.overview()
    assert overview["local"]["total"] == 8
    assert overview["peers"][0]["total"] == 4 and overview["peers"][0]["name"] == "one"
    assert overview["school_wide"]["total"] == 12
    assert overview["school_wide"]["by_severity"] == {"MEDIUM": 8, "HIGH": 4}
    assert one.facade.overview()["school_wide"]["total"] == 12
    # visible through the real HTTP API too
    api_view = RemoteServerClient(two.address, two.token, retries=0).sync_overview()
    assert api_view["school_wide"]["total"] == 12


def test_status_changes_and_footage_flag_update_the_remote_copy_once(nodes):
    one, two = nodes("one"), nodes("two")
    two.connect(one)
    incident = one.fight()
    two.sync.sync_once()
    one.repo.attach_incident_footage(incident["public_id"], "/some/clip.mp4")
    one.repo.update_incident_status(incident["public_id"], "CONFIRMED")
    two.sync.sync_once()
    alerts = two.facade.remote_alerts(10)
    assert len(alerts) == 1 and alerts[0]["status"] == "CONFIRMED" and alerts[0]["has_footage"]
    assert len(two.new_alerts) == 1       # an update is not a new alert


def test_duplicate_and_out_of_order_delivery_is_ignored(nodes):
    two = nodes("two")
    event = {"incident_id": "INC-00001", "camera_id": "C", "camera_name": "C", "happened_at": "2026-01-01T00:00:00+00:00",
             "event": "Fight", "confidence": 0.9, "severity": "HIGH", "status": "NEW", "has_footage": True, "seq": 5}
    assert two.repo.upsert_remote_alert("id-x", "x", event) == "new"
    assert two.repo.upsert_remote_alert("id-x", "x", event) == "same"
    assert two.repo.upsert_remote_alert("id-x", "x", {**event, "seq": 3, "status": "DISMISSED"}) == "same"
    assert two.repo.upsert_remote_alert("id-x", "x", {**event, "seq": 6, "status": "RESOLVED"}) == "updated"
    assert two.repo.upsert_remote_alert("id-y", "y", event) == "new"      # same incident id, different server
    assert len(two.repo.list_remote_alerts()) == 2


def test_disconnected_server_keeps_detecting_and_catches_up_after_reconnect(nodes, tmp_path):
    one = nodes("one")
    two = nodes("two")
    two.connect(one)
    one.fight("CAM-01")
    two.sync.sync_once()
    assert two.facade.overview()["peers"][0]["state"] == STATE_ONLINE
    port = one.api.port
    one.api.stop()                                   # server one drops off the network
    missed = [one.fight(f"CAM-{n:02d}") for n in (2, 3, 4)]     # ...but keeps detecting locally
    assert len(one.repo.list_incidents()) == 4
    two.sync.sync_once()
    peer = two.facade.overview()["peers"][0]
    assert peer["state"] == STATE_DISCONNECTED and peer["last_error"]
    assert len(two.facade.remote_alerts(10)) == 1     # earlier alerts stay visible while offline
    two.fight("CAM-77")                               # server two keeps detecting too
    assert len(two.repo.list_incidents()) == 1
    # server one comes back on the same address
    one.api = ApiServer("127.0.0.1", port, one.token, SyncBackend(one.facade))
    one.api.start()
    two.sync._next_try.clear()
    two.sync.sync_once()
    assert two.facade.overview()["peers"][0]["state"] == STATE_ONLINE
    assert {a["incident_id"] for a in two.facade.remote_alerts(10)} >= {m["public_id"] for m in missed}
    assert two.facade.overview()["school_wide"]["total"] == 5


def test_three_servers_full_mesh_with_one_school_id(nodes):
    a, b, c = nodes("a"), nodes("b"), nodes("c")
    for x in (a, b, c):
        for y in (a, b, c):
            if x is not y:
                x.connect(y)
    a.fight("CAM-01")
    b.fight("CAM-02")
    c.fight("CAM-03")
    for _ in range(2):
        for x in (a, b, c):
            x.sync.sync_once()
    for x in (a, b, c):
        overview = x.facade.overview()
        assert overview["school_wide"]["total"] == 3
        assert overview["local"]["total"] == 1 and len(overview["peers"]) == 2
        assert {p["name"] for p in overview["peers"]} == {"a", "b", "c"} - {x.name}


def test_other_school_and_bad_token_are_rejected(nodes):
    one = nodes("one")
    stranger = nodes("stranger", school="another-school")
    two = nodes("two")
    stranger.fight()
    two.connect(stranger)
    two.connect(one, token="x" * 32)                 # right school ID but wrong token
    one.fight()
    two.sync.sync_once()
    states = {p["name"]: p["state"] for p in two.facade.overview()["peers"]}
    assert states == {"stranger": STATE_WRONG_SCHOOL, "one": STATE_UNAUTHORIZED}
    assert two.facade.remote_alerts(10) == []        # knowing a school ID alone grants nothing


def test_one_dead_peer_does_not_block_the_others(nodes):
    one, two = nodes("one"), nodes("two")
    two.peers.append({"name": "ghost", "address": "http://127.0.0.1:9", "ca_file": ""})
    two.tokens["http://127.0.0.1:9"] = "g" * 32
    two.connect(one)
    one.fight()
    two.sync.sync_once()
    states = {p["name"]: p["state"] for p in two.facade.overview()["peers"]}
    assert states["one"] == STATE_ONLINE and states["ghost"] == STATE_DISCONNECTED
    assert len(two.facade.remote_alerts(10)) == 1


def test_database_reset_on_the_source_resyncs_without_double_counting(nodes, tmp_path):
    one, two = nodes("one"), nodes("two")
    two.connect(one)
    one.fight("CAM-01")
    two.sync.sync_once()
    cursor = two.repo.list_peer_states()[0]["last_seq"]
    assert cursor == 1
    # pretend server two remembers a cursor far ahead of a freshly reset server one
    two.repo.save_peer_state("id-one", "one", one.address, 500, "online", None)
    two.sync.sync_once()
    assert two.repo.list_peer_states()[0]["last_seq"] == 1
    assert len(two.facade.remote_alerts(10)) == 1


def test_large_backlog_is_paged_and_removed_peers_are_forgotten(nodes):
    one, two = nodes("one"), nodes("two")
    two.connect(one)
    cam = CameraConfig("CAM-1", "C", "RTSP", "r", True, "n")
    for i in range(PAGE_SIZE + 30):
        row = one.repo.create_incident(cam, "Fight", 0.8, "MEDIUM", 0)
        one.repo.update_incident_status(row["public_id"], "RESOLVED")
    two.sync.sync_once()
    assert len(two.repo.list_remote_alerts(1000)) == PAGE_SIZE + 30
    two.peers.clear()
    two.sync.sync_once()
    assert two.repo.list_remote_alerts() == [] and two.repo.list_peer_states() == []


def test_footage_is_never_transmitted_and_remote_alert_has_no_clip_route(nodes):
    one, two = nodes("one"), nodes("two")
    two.connect(one)
    incident = one.fight()
    one.repo.attach_incident_footage(incident["public_id"], str(one.repo.footage_dir / "clip.mp4"))
    two.sync.sync_once()
    alert = two.facade.remote_alerts(1)[0]
    assert alert["has_footage"] and alert["footage_location"] == "source_server"
    assert not list(two.repo.footage_dir.iterdir())            # nothing copied locally
    assert set(one.facade.events(0, 10)["events"][0]) == {
        "incident_id", "camera_id", "camera_name", "happened_at", "event", "confidence",
        "severity", "status", "has_footage", "seq"}


def test_sync_thread_start_stop_and_isolation(nodes):
    one, two = nodes("one"), nodes("two")
    two.connect(one)
    one.fight()
    two.sync.start()
    deadline = time.time() + 5
    while time.time() < deadline and not two.facade.remote_alerts(1):
        time.sleep(0.05)
    assert two.facade.remote_alerts(1)
    two.sync.stop()
    assert two.sync._thread is None
