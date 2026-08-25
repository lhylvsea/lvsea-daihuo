import unittest

from scripts.route_request import build_plan
from scripts.validate_flow import validate_artifact_manifest, validate_request


class FlowContractTests(unittest.TestCase):
    def test_preview_without_assets_is_explicitly_degraded(self) -> None:
        request = {
            "product": {
                "name": "测试商品",
                "facts": [{"text": "规格已由用户提供", "status": "user_asserted"}],
                "assets": [],
            },
            "goal": {"platform": "douyin", "duration_sec": 25, "aspect_ratio": "9:16"},
            "mode": "preview",
            "permissions": {"allow_paid": False, "allow_publish": False},
        }
        plan = build_plan(request)
        self.assertEqual(plan["status"], "preview")
        self.assertIn("product.assets", plan["missing_evidence"])
        self.assertFalse(plan["publish_allowed"])

    def test_request_contract_rejects_missing_facts(self) -> None:
        errors = validate_request({"product": {"name": "测试"}, "goal": {"platform": "douyin", "duration_sec": 20}})
        self.assertIn("product.facts must be a non-empty list", errors)

    def test_ready_requires_human_and_gate_evidence(self) -> None:
        errors = validate_artifact_manifest({
            "skill": "lvsea-daihuo",
            "status": "ready",
            "final_video": "video/final.mp4",
            "gate_status": "pass",
            "human_reviewed": True,
            "missing_evidence": [],
        })
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
