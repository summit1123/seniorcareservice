from __future__ import annotations

import unittest

from src.webapp.contest_demo_view import render_contest_demo_page
from src.webapp.customer_decision_app import load_dashboard_bundle, render_webapp_page


class TestContestDemoView(unittest.TestCase):
    def test_contest_demo_page_shows_data_policy_and_llm_status(self) -> None:
        bundle = load_dashboard_bundle()
        html = render_contest_demo_page(bundle)

        self.assertIn("Senior Safe Mileage 공모전 데모", html)
        self.assertIn("data/fixtures/senior_trip_logs.csv", html)
        self.assertIn("1,389건", html)
        self.assertIn("30명", html)
        self.assertIn("90일 관측", html)
        self.assertIn("baseline 60일 + recent 30일", html)
        report_mode = str(bundle["llm_report_service_status"]["report_mode"])
        self.assertIn(report_mode, html)
        if report_mode == "llm_generated":
            self.assertIn("OpenAI API 호출 활성", html)
            self.assertIn("식별자 없는 요약 피처만 전송", html)
        else:
            self.assertIn("실제 OpenAI API 호출 없음", html)
            self.assertIn(".env의 OPENAI_API_KEY는 이번 산출물 생성에서 사용하지 않음", html)
        self.assertIn("policy_30_30_20_20_p20_a75", html)
        self.assertIn("5/5 포착", html)
        self.assertIn("114개 후보 비교", html)
        self.assertIn('href="/detail"', html)
        self.assertIn('href="/api/validation"', html)

    def test_contest_demo_page_lists_all_six_persona_cases(self) -> None:
        html = render_contest_demo_page(load_dashboard_bundle())

        self.assertIn("생활권 안 저주행 안정형", html)
        self.assertIn("최근 생활권 밖 위험변화형", html)
        self.assertIn("생활권 밖 안정 주행형", html)
        self.assertIn("생활권 안 저주행 위험행동형", html)
        self.assertIn("병원 방문 반복 외부 목적지형", html)
        self.assertIn("가족 돌봄 불규칙 외부 이동형", html)

    def test_webapp_root_is_contest_page_and_detail_keeps_operator_view(self) -> None:
        bundle = load_dashboard_bundle()
        root_html = render_webapp_page("/", bundle)
        detail_html = render_webapp_page("/detail?customer_id=cust_011", bundle)

        self.assertIn("공모전 시연용 화면", root_html)
        self.assertIn("데이터는 실제로 만들어졌나", root_html)
        self.assertNotIn("Senior Safe Mileage 정책/검증 대시보드", root_html)
        self.assertIn("Senior Safe Mileage 정책/검증 대시보드", detail_html)
        self.assertIn("cust_011", detail_html)
        self.assertNotIn("공모전 시연용 화면", detail_html)


if __name__ == "__main__":
    unittest.main()
