const pptxgen = require("pptxgenjs");
const fs = require("fs");
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
s.addText("Q. 거리가 같으면 보험료도 같아야 하는 것 아닌가?", {
  x: 3.7, y: 0.35, w: 6.0, h: 0.33, fontFace: KO, fontSize: 13.5, color: MUTED
});

// ── 결론 ──
s.addText([
  { text: "기존 마일리지에서는 둘 다 16% 할인. ", options: { color: INK } },
  { text: "저희 산식에서는 22.6% 와 3%", options: { color: ACCENT } },
  { text: "로 갈립니다.", options: { color: INK } }
], {
  x: 0.45, y: 0.82, w: 12.4, h: 0.5, fontFace: KO, fontSize: 20, bold: true
});
s.addText("연 주행거리가 2,511km와 2,474km로 거의 같은 두 시니어입니다. 갈린 이유는 거리가 아니라 생활권 밖 비중과 위험행동이 함께 변했는지입니다.", {
  x: 0.45, y: 1.34, w: 12.4, h: 0.3, fontFace: KO, fontSize: 11.5, color: MUTED
});

// ── 좌우 인물 카드 ──
function person(x, tone, tag, name, meta, facts, capture, capH) {
  const hi = tone === "good" ? GOOD : WARN;
  s.addShape(pres.ShapeType.roundRect, {
    x: x, y: 1.78, w: 6.18, h: 4.28, fill: { color: "FFFFFF" }, line: { color: "E3E7EF", width: 1.2 }, rectRadius: 0.1
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
  // 대시보드 캡처
  s.addImage({
    path: capture, x: x + 0.18, y: 3.42, w: 5.82, h: capH
  });
}

person(0.45, "good", "우대", "Ruth Miller (b. 1956)",
  "고밀도 도심 · 복수 생활권형 · 연 2,511km",
  [
    { label: "생활권 밖 비중", value: "0.0%", hi: true },
    { label: "위험행동", value: "13건", hi: true },
    { label: "케어 발동", value: "없음" }
  ],
  DIR + "tariff_favorable_ruth.png", 2.11);

person(6.87, "warn", "예방 케어", "Edward Clark (b. 1953)",
  "고밀도 도심 · 동시변화형 · 연 2,474km",
  [
    { label: "생활권 밖 비중", value: "7.3%", hi: true },
    { label: "위험행동", value: "209건", hi: true },
    { label: "케어 발동", value: "1개월", hi: true }
  ],
  DIR + "tariff_care_edward.png", 2.23);

// ── 하단 결론 바 ──
s.addShape(pres.ShapeType.roundRect, {
  x: 0.45, y: 6.28, w: 12.4, h: 0.56, fill: { color: CARD }, line: { color: CARD }, rectRadius: 0.08
});
s.addText([
  { text: "거리가 아니라 행동입니다 — ", options: { bold: true, color: INK } },
  { text: "생활권 안에서 안전하게 다니면 할인이 넓어지고(연 ₩63,648 절약), 이동과 위험행동이 같은 달에 함께 변하면 그 달의 보너스가 멈춥니다(연 ₩106,080 차이). ", options: { color: BODY } },
  { text: "할증 경로는 없고 기준 요율이 하한입니다.", options: { bold: true, color: ACCENT } }
], {
  x: 0.68, y: 6.38, w: 11.95, h: 0.38, fontFace: KO, fontSize: 10.5
});

s.addText("실제 대시보드 화면 캡처 · 합성 시뮬레이션 결과이며 확정 요율이 아닙니다 · 달러는 예시 환율(1$≈₩1,350) 환산", {
  x: 0.45, y: 6.96, w: 12.4, h: 0.22, fontFace: KO, fontSize: 8.5, color: "9AA3B2"
});

s.addNotes("같은 저주행(2,511km vs 2,474km), 기존 마일리지에서 둘 다 16% 할인. 우리 산식에서 22.6% vs 3%로 갈림. 갈린 이유는 생활권 밖 비중(0% vs 7.3%)과 위험행동(13건 vs 209건)의 동시 변화. 할증 경로 없음, 기준 요율이 하한.");

pres.writeFile({ fileName: DIR + "Appendix_Tariff.pptx" }).then((f) => console.log("saved:", f));
