from app.access import (
    Principal,
    can_edit_session,
    feature_access,
    normalize_role,
    visible_sessions,
)

ORG = "org_1"
ME = Principal(user_id="user_me", org_id=ORG, role="developer")
ADMIN = Principal(user_id="user_admin", org_id=ORG, role="admin")

TEAMS = {"payments": "Payments", "platform": "Platform", "qa": "QA"}
MEMBERS = {
    "payments": {"user_me", "user_asha", "user_ben"},
    "platform": {"user_ben", "user_chen"},
    "qa": {"user_dana"},
}
SESSIONS = [
    {"id": "s1", "user_id": "user_me"},
    {"id": "s2", "user_id": "user_asha"},
    {"id": "s3", "user_id": "user_ben"},
    {"id": "s4", "user_id": "user_chen"},
    {"id": "s5", "user_id": "user_dana"},
]


def test_normalize_role():
    assert normalize_role("org:admin") == "admin"
    assert normalize_role("admin") == "admin"
    assert normalize_role("member") == "developer"
    assert normalize_role("org:qa") == "qa"
    assert normalize_role("something_custom") == "developer"
    assert normalize_role(None) == "developer"


def test_feature_access_admin_always():
    assert feature_access(ADMIN, feature_team_ids=[], my_team_ids=[], assignee_ids=[]) == "admin"


def test_feature_access_direct_assignment():
    assert (
        feature_access(ME, feature_team_ids=["platform"], my_team_ids=["payments"], assignee_ids=["user_me"])
        == "assigned"
    )


def test_feature_access_via_team():
    assert (
        feature_access(ME, feature_team_ids=["payments", "qa"], my_team_ids=["payments"], assignee_ids=[])
        == "team"
    )


def test_feature_access_denied():
    assert feature_access(ME, feature_team_ids=["platform"], my_team_ids=["payments"], assignee_ids=["user_x"]) is None


def test_visible_sessions_admin_sees_all():
    out = visible_sessions(ADMIN, SESSIONS, feature_team_ids=[], my_team_ids=[], team_members={})
    assert [s["id"] for s, _ in out] == ["s1", "s2", "s3", "s4", "s5"]
    assert {r for _, r in out} == {"admin"}


def test_visible_sessions_own_plus_shared_team():
    # PAYMENT feature is attached to Payments + QA; I am on Payments only.
    out = visible_sessions(
        ME,
        SESSIONS,
        feature_team_ids=["payments", "qa"],
        my_team_ids=["payments"],
        team_members=MEMBERS,
        team_names=TEAMS,
    )
    assert {(s["id"], r) for s, r in out} == {
        ("s1", "own"),
        ("s2", "team:Payments"),
        ("s3", "team:Payments"),
    }
    # Chen (Platform only) and Dana (QA, a team I'm not on) are hidden.


def test_visible_sessions_direct_assignee_sees_only_own():
    # LOGIN feature is attached to Platform; I'm directly assigned but not on Platform.
    out = visible_sessions(
        ME,
        SESSIONS,
        feature_team_ids=["platform"],
        my_team_ids=["payments"],
        team_members=MEMBERS,
        team_names=TEAMS,
    )
    assert [(s["id"], r) for s, r in out] == [("s1", "own")]


def test_can_edit_session():
    assert can_edit_session(ME, {"user_id": "user_me"})
    assert not can_edit_session(ME, {"user_id": "user_asha"})
    assert can_edit_session(ADMIN, {"user_id": "user_asha"})
