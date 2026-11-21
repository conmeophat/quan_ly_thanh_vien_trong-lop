"""Regression tests for tenant-like per-group privacy and role enforcement."""

import tempfile
import unittest
from pathlib import Path

import database as db
from security import PasswordPolicyError


class PermissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(cls.temp_dir.name) / "test.sqlite3"

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def setUp(self):
        db.DB_PATH.unlink(missing_ok=True)
        db.DB_PATH.with_suffix(".sqlite3-wal").unlink(missing_ok=True)
        db.DB_PATH.with_suffix(".sqlite3-shm").unlink(missing_ok=True)
        db.init_db()
        self.founder_id = db.create_founder(
            "Founder", "0900000001", "FounderStrongPass!2026", local_setup_allowed=True
        )
        self.founder = db.get_user_by_id(self.founder_id)
        self.teacher_id = db.create_user(
            self.founder, "Teacher", "0900000002", "TeacherStrongPass!2026", "teacher", None
        )
        self.teacher = db.get_user_by_id(self.teacher_id)
        self.leader1_id = db.create_user(
            self.founder, "Leader One", "0900000003", "LeaderOneStrong!2026", "leader", 1
        )
        self.leader2_id = db.create_user(
            self.founder, "Leader Two", "0900000004", "LeaderTwoStrong!2026", "leader", 2
        )
        self.leader1 = db.get_user_by_id(self.leader1_id)
        self.leader2 = db.get_user_by_id(self.leader2_id)
        self.member1_id = db.create_user(
            self.leader1, "Member One", "0900000005", "MemberOneStrong!2026", "member", 1
        )
        self.member2_id = db.create_user(
            self.leader2, "Member Two", "0900000006", "MemberTwoStrong!2026", "member", 2
        )
        self.member1 = db.get_user_by_id(self.member1_id)
        self.member2 = db.get_user_by_id(self.member2_id)

    def test_leader_cannot_list_or_summarize_other_groups(self):
        own = db.list_group_members(self.leader1, 1)
        self.assertEqual([x["id"] for x in own], [self.member1_id])
        with self.assertRaises(db.PermissionDenied):
            db.list_group_members(self.leader1, 2)
        summaries = db.group_summaries(self.leader1)
        self.assertEqual([x["group_no"] for x in summaries], [1])
        visible_accounts = db.list_visible_accounts(self.leader1)
        self.assertEqual({x["id"] for x in visible_accounts}, {self.member1_id})

    def test_leader_cannot_read_or_change_other_group_member(self):
        with self.assertRaises(db.PermissionDenied):
            db.member_summary(self.leader1, self.member2_id)
        with self.assertRaises(db.PermissionDenied):
            db.records_for_member(self.leader1, self.member2_id)
        with self.assertRaises(db.PermissionDenied):
            db.add_score(self.leader1, self.member2_id, 2, "Khen thưởng", "Không được phép")
        with self.assertRaises(db.PermissionDenied):
            db.add_evaluation(self.leader1, self.member2_id, "Không được phép")

    def test_leader_can_manage_own_group_only(self):
        score_id = db.add_score(self.leader1, self.member1_id, 2, "Khen thưởng", "Đi học đúng giờ")
        eval_id = db.add_evaluation(self.leader1, self.member1_id, "Có ý thức học tập tốt.")
        scores, evaluations = db.records_for_member(self.leader1, self.member1_id)
        self.assertEqual(scores[0]["id"], score_id)
        self.assertEqual(evaluations[0]["id"], eval_id)
        db.edit_score(self.leader1, self.member1_id, score_id, 3, "Khen thưởng", "Đã xác minh")
        db.edit_evaluation(self.leader1, self.member1_id, eval_id, "Nhận xét đã cập nhật.")
        summary = db.member_summary(self.leader1, self.member1_id)
        self.assertEqual(summary["total_points"], 3.0)
        db.delete_score(self.leader1, self.member1_id, score_id)
        db.delete_evaluation(self.leader1, self.member1_id, eval_id)
        self.assertEqual(db.member_summary(self.leader1, self.member1_id)["total_points"], 0.0)

    def test_member_can_only_view_self(self):
        db.add_score(self.leader1, self.member1_id, 1, "Nề nếp", "Tích cực")
        own_scores, _, own_total = db.my_records(self.member1_id)
        self.assertEqual(len(own_scores), 1)
        self.assertEqual(own_total, 1.0)
        with self.assertRaises(db.PermissionDenied):
            db.records_for_member(self.member1, self.member2_id)
        with self.assertRaises(db.PermissionDenied):
            db.list_group_members(self.member1, 1)
        visible = db.list_visible_accounts(self.member1)
        self.assertEqual([x["id"] for x in visible], [self.member1_id])

    def test_teacher_and_founder_have_class_wide_visibility(self):
        self.assertEqual({x["group_no"] for x in db.group_summaries(self.teacher)}, {1, 2, 3, 4})
        self.assertEqual({x["group_no"] for x in db.group_summaries(self.founder)}, {1, 2, 3, 4})
        self.assertEqual(db.member_summary(self.teacher, self.member2_id)["id"], self.member2_id)
        self.assertEqual(db.member_summary(self.founder, self.member1_id)["id"], self.member1_id)

    def test_phone_number_is_unique(self):
        with self.assertRaises(db.ValidationError):
            db.create_user(self.teacher, "Duplicate Person", "0900000005",
                           "NewPersonStrong!2026", "member", 1)

    def test_leader_cannot_create_account_in_another_group(self):
        with self.assertRaises(db.PermissionDenied):
            db.create_user(self.leader1, "Outsider", "0900000008",
                           "OutsiderStrong!2026", "member", 2)
        new_id = db.create_user(self.leader1, "New Member", "0900000007",
                                "NewMemberStrong!2026", "member", 1)
        self.assertEqual(db.get_user_by_id(new_id)["group_no"], 1)

    def test_leader_cannot_create_account_in_another_group(self):
        with self.assertRaises(db.PermissionDenied):
            db.create_user(self.leader1, "Outsider", "outsider01", "OUT01",
                           "OutsiderStrong!2026", "member", 2)
        new_id = db.create_user(self.leader1, "New Member", "member03", "M003",
                                "NewMemberStrong!2026", "member", 1)
        self.assertEqual(db.get_user_by_id(new_id)["group_no"], 1)

    def test_five_wrong_logins_lock_the_account(self):
        for _ in range(5):
            user, message = db.authenticate("0900000005", "wrong-password")
            self.assertIsNone(user)
        user, message = db.authenticate("0900000005", "MemberOneStrong!2026")
        self.assertIsNone(user)
        self.assertIn("khóa", message.lower())

    def test_admin_cannot_create_second_active_leader_in_same_group(self):
        with self.assertRaises(db.ValidationError):
            db.create_user(self.teacher, "Second Leader", "0900000009",
                           "SecondLeaderStrong!2026", "leader", 1)

    def test_teacher_can_edit_a_member_account_and_revoke_old_session(self):
        old_version = self.member1["session_version"]
        db.update_account(self.teacher, self.member1_id, "Member One Updated", "0900000010",
                          "member", 3)
        updated = db.get_user_by_id(self.member1_id)
        self.assertEqual(updated["group_no"], 3)
        self.assertEqual(updated["full_name"], "Member One Updated")
        self.assertGreater(updated["session_version"], old_version)
        with self.assertRaises(db.PermissionDenied):
            db.member_summary(self.leader1, self.member1_id)

    def test_deactivated_leader_cannot_keep_using_stale_authorization(self):
        db.set_account_active(self.founder, self.leader1_id, False)
        with self.assertRaises(db.PermissionDenied):
            db.list_group_members(self.leader1, 1)

    def test_only_one_active_homeroom_teacher_can_exist(self):
        with self.assertRaises(db.ValidationError):
            db.create_user(self.founder, "Second Teacher", "0900000011",
                           "SecondTeacherStrong!2026", "teacher", None)

    def test_eight_character_password_is_accepted_and_shorter_is_rejected(self):
        new_id = db.create_user(self.teacher, "Eight Char", "0900000012",
                                "Password", "member", 1)
        self.assertIsNotNone(db.get_user_by_id(new_id))
        with self.assertRaises(PasswordPolicyError):
            db.create_user(self.teacher, "Short Password", "0900000013",
                           "short7", "member", 1)

    def test_only_founder_and_teacher_can_change_or_reset_passwords(self):
        with self.assertRaises(db.PermissionDenied):
            db.change_own_password(self.leader1, self.leader1_id,
                                   "LeaderOneStrong!2026", "NewLeaderPass88")
        with self.assertRaises(db.PermissionDenied):
            db.change_own_password(self.member1, self.member1_id,
                                   "MemberOneStrong!2026", "NewMemberPass88")
        with self.assertRaises(db.PermissionDenied):
            db.admin_reset_password(self.leader1, self.member1_id, "ResetPass88")
        db.admin_reset_password(self.teacher, self.member1_id, "ResetPass88")
        user, message = db.authenticate("0900000005", "ResetPass88")
        self.assertIsNotNone(user)

        db.change_own_password(self.founder, self.founder_id,
                               "FounderStrongPass!2026", "FounderNewPass88")
        user, message = db.authenticate("0900000001", "FounderNewPass88")
        self.assertIsNotNone(user)


if __name__ == "__main__":
    unittest.main(verbosity=2)
