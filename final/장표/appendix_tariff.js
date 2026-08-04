const pptxgen = require("pptxgenjs");
const DIR = "/private/tmp/claude-501/-Users-gimdonghyeon-Desktop-seniorcareservice/60c72b2a-4eb8-48cb-9a78-503f6e83abe3/scratchpad/";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";

const KO = "맑은 고딕";
const INK = "1A2330";
const MUTED = "6B7280";
const BODY = "44506A";
const ACCENT = "5B21B6";
const CARD = "F4F5F9";
const GOOD = "0F766E";
const WARN = "B45309";

const s = pres.addSlide();
s.background = { color: "FFFFFF" };

// ── 헤더 ──
s.addText("Appendix - 요율", {
  x: 0.45, y: 0.24, w: 3.4, h: 0.48, fontFace: KO, fontSize: 25, bold: true, color: INK
});
s.addText("Q. 케어가 열리면 보험료가 오르는 것 아닌가?", {
  x: 3.7, y: 0.35, w: 6.0, h: 0.33, fontFace: KO, fontSize: 13.5, color: MUTED
});

// ── 결론 ──
s.addText([
  { text: "기존 마일리지로는 둘 다 663,600원 — ", options: { color: INK } },
  { text: "행동이 달라 할인 폭이 25.5%와 8%", options: { color: ACCENT } },
  { text: "로 갈립니다.", options: { color: INK } }
], {
  x: 0.45, y: 0.82, w: 12.4, h: 0.5, fontFace: KO, fontSize: 19, bold: true
});
s.addText("같은 1951년생 · 같은 차종(기본보험료 84만원) · 같은 광역 저밀도 환경 · 연 주행 6,793km vs 6,789km(차이 0.1%) · 생활권 밖 비중도 28.7% vs 29.6%로 비슷 — 다른 것은 위험행동뿐입니다.", {
  x: 0.45, y: 1.34, w: 12.4, h: 0.3, fontFace: KO, fontSize: 11, color: MUTED
});

// ── 좌우 인물 카드 ──
function person(x, tone, tag, name, meta, facts, verdict, capture, capH) {
  const hi = tone === "good" ? GOOD : WARN;
  s.addShape(pres.ShapeType.roundRect, {
    x: x, y: 1.78, w: 6.18, h: 4.5, fill: { color: "FFFFFF" }, line: { color: "E3E7EF", width: 1.2 }, rectRadius: 0.1
  });
  s.addShape(pres.ShapeType.roundRect, {
    x: x + 0.22, y: 1.95, w: 1.15, h: 0.3, fill: { color: tone === "good" ? "E6F4F1" : "FBF0E2" }, line: { color: tone === "good" ? "E6F4F1" : "FBF0E2" }, rectRadius: 0.14
  });
  s.addText(tag, {
    x: x + 0.22, y: 1.97, w: 1.15, h: 0.26, fontFace: KO, fontSize: 10, bold: true, color: hi, align: "center"
  });
  s.addText(name, {
    x: x + 1.5, y: 1.93, w: 4.5, h: 0.32, fontFace: KO, fontSize: 15, bold: true, color: INK
  });
  s.addText(meta, {
    x: x + 0.22, y: 2.32, w: 5.7, h: 0.26, fontFace: KO, fontSize: 10.5, color: MUTED
  });
  // 행동 지표 3칸
  facts.forEach((f, i) => {
    const fx = x + 0.22 + i * 1.94;
    s.addShape(pres.ShapeType.roundRect, {
      x: fx, y: 2.64, w: 1.82, h: 0.66, fill: { color: CARD }, line: { color: CARD }, rectRadius: 0.07
    });
    s.addText(f.label, {
      x: fx + 0.12, y: 2.7, w: 1.6, h: 0.22, fontFace: KO, fontSize: 9, color: MUTED
    });
    s.addText(f.value, {
      x: fx + 0.12, y: 2.9, w: 1.6, h: 0.3, fontFace: KO, fontSize: 13, bold: true, color: f.hi ? hi : INK
    });
  });
  // 판정 한 줄 (할인 프레임)
  s.addText(verdict, {
    x: x + 0.22, y: 3.42, w: 5.75, h: 0.26, fontFace: KO, fontSize: 10.5, bold: true, color: hi
  });
  // 대시보드 캡처
  s.addImage({
    path: capture, x: x + 0.18, y: 3.74, w: 5.82, h: capH
  });
}

person(0.45, "good", "우대", "Kenneth Young (b. 1951)",
  "광역 저밀도 · 이동변화·안전유지형 · 연 6,793km",
  [
    { label: "위험행동", value: "0건", hi: true },
    { label: "생활권 밖 비중", value: "28.7%" },
    { label: "케어 발동", value: "없음" }
  ],
  "할인 확대 21% → 25.5% · 연 ₩37,632 덜 냅니다",
  DIR + "tariff_reward_kenneth.png", 2.25);

person(6.87, "warn", "예방 케어", "Sylvia Moore (b. 1951)",
  "광역 저밀도 · 동시변화형 · 연 6,789km",
  [
    { label: "위험행동", value: "137건", hi: true },
    { label: "생활권 밖 비중", value: "29.6%" },
    { label: "케어 발동", value: "1개월", hi: true }
  ],
  "할인 축소 21% → 8% · 여전히 기준(84만원)보다 낮음",
  DIR + "tariff_care_sylvia.png", 2.4);

// ── 하단 결론 바 ──
s.addShape(pres.ShapeType.roundRect, {
  x: 0.45, y: 6.5, w: 12.4, h: 0.56, fill: { color: CARD }, line: { color: CARD }, rectRadius: 0.08
});
s.addText([
  { text: "할증이 아니라 할인 축소입니다 — ", options: { bold: true, color: INK } },
  { text: "8%도 할인이며, 어떤 경우에도 보험료가 기준 보험료(84만원)를 넘지 않습니다(180건 중 할증 0건). 케어가 닫히고 기준선으로 복귀하면 할인은 다시 넓어집니다.", options: { color: BODY } }
], {
  x: 0.68, y: 6.6, w: 11.95, h: 0.38, fontFace: KO, fontSize: 10.5
});

s.addText("실제 대시보드 화면 캡처 · 합성 시뮬레이션 결과이며 확정 요율이 아닙니다 · 달러는 예시 환율(1$≈₩1,350) 환산", {
  x: 0.45, y: 7.14, w: 12.4, h: 0.22, fontFace: KO, fontSize: 8.5, color: "9AA3B2"
});

s.addNotes("동일 조건 통제 페어: 같은 1951년생, 같은 기본보험료 840,000원(같은 차종), 같은 광역 저밀도 환경, 거리 차 0.1%, 밖 비중도 비슷(28.7 vs 29.6%). 기존 마일리지에서는 둘 다 21% 할인 = 663,600원으로 동일. 다른 것은 위험행동(0건 vs 137건)과 동시변화 여부뿐 → 25.5%(625,968원) vs 8%(772,800원). 핵심 방어: 8%도 할인이다. 할증 경로가 없고 하한은 기준 요율 — 180건 중 기준보험료 초과 0건. 케어 해제(기준선 복귀) 시 할인 복원.");

pres.writeFile({ fileName: DIR + "Appendix_Tariff.pptx" }).then((f) => console.log("saved:", f));
