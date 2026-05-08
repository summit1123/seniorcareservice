from __future__ import annotations

import unittest

from src.webapp.contest_demo_view import render_contest_demo_page
from src.webapp.customer_decision_app import load_dashboard_bundle, render_webapp_page


class TestContestDemoView(unittest.TestCase):
    def test_contest_demo_page_shows_data_policy_and_llm_status(self) -> None:
        bundle = load_dashboard_bundle()
        html = render_contest_demo_page(bundle)

        self.assertIn("시니어 안심주행 보험 검증 대시보드", html)
        self.assertIn("한 문장으로 보면", html)
        self.assertIn("기존 마일리지 시스템과 무엇이 다른가", html)
        self.assertIn("기존 마일리지 보험", html)
        self.assertIn("시니어 안심주행 방식", html)
        self.assertIn("우리가 실제로 테스트한 질문", html)
        self.assertIn("테스트 실행 로그", html)
        self.assertIn("Q1", html)
        self.assertIn("Q2", html)
        self.assertIn("Q3", html)
        self.assertIn("Q4", html)
        self.assertIn("data/fixtures/senior_trip_logs.csv", html)
        self.assertIn("1,389건", html)
        self.assertIn("30명", html)
        self.assertIn("90일 관측", html)
        self.assertIn("이전 60일 + 최근 30일", html)
        self.assertIn("좌표로 보는 생활권 모델", html)
        self.assertIn("직접 돌려보는 조건 테스트", html)
        self.assertIn("고객과 최근 주행 조건을 바꿔보기", html)
        self.assertIn("name=\"recent_out_zone_ratio_pct\"", html)
        self.assertIn("위험변화 점수", html)
        self.assertIn("고객 011의 90일 주행 좌표", html)
        self.assertIn("모델이 실제로 보는 4가지 판단 요소", html)
        self.assertIn("기존 방식 0/5 · 제안 방식 5/5", html)
        self.assertIn("OpenAI 설명문 생성", html)
        self.assertIn("분석 에이전트 실행 흐름", html)
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

        self.assertIn("테스트 결과를 먼저 보여주는 공모전 시연 화면", root_html)
        self.assertIn("한 문장으로 보면", root_html)
        self.assertIn("기존 마일리지 시스템과 무엇이 다른가", root_html)
        self.assertIn("테스트 실행 로그", root_html)
        self.assertIn("데이터 증거", root_html)
        self.assertNotIn("Senior Safe Mileage 정책/검증 대시보드", root_html)
        self.assertIn("Senior Safe Mileage 정책/검증 대시보드", detail_html)
        self.assertIn("cust_011", detail_html)
        self.assertNotIn("테스트 결과를 먼저 보여주는 공모전 시연 화면", detail_html)

    def test_contest_demo_simulation_query_changes_selected_customer_and_conditions(self) -> None:
        bundle = load_dashboard_bundle()
        html = render_contest_demo_page(
            bundle,
            request_path=(
                "/?customer_id=cust_001&annualized_recent_km=4200"
                "&recent_out_zone_ratio_pct=5&night_delta_pct=0"
                "&risk_rate_delta_per_100km=0&risk_signal_count=0"
            ),
        )

        self.assertIn("고객 001의 90일 주행 좌표", html)
        self.assertIn("value=\"4200\"", html)
        self.assertIn("value=\"5\"", html)
        self.assertIn("원래 판정과 같은 우대입니다.", html)
        self.assertIn("기존 저주행 할인", html)


if __name__ == "__main__":
    unittest.main()
