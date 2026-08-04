const pptxgen = require("pptxgenjs");

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.3 x 7.5

const KO = "맑은 고딕";
const INK = "1A2330";
const MUTED = "6B7280";
const BODY = "44506A";
const ACCENT = "5B21B6";
const CARD = "F4F5F9";
const BAR = "C9D2E6";
const BAR_HI = "5B21B6";
const GOOD = "0F766E";

const s = pres.addSlide();
s.background = { color: "FFFFFF" };

// ── 헤더 ──
s.addText("Appendix - C", {
  x: 0.45, y: 0.24, w: 3.2, h: 0.48, fontFace: KO, fontSize: 25, bold: true, color: INK
});
s.addText("Q. 가중치가 왜 30 : 30 : 20 : 20 인가?", {
  x: 3.45, y: 0.35, w: 5.5, h: 0.33, fontFace: KO, fontSize: 13.5, color: MUTED
});

// ── 결론 ──
s.addText([
  { text: "정답을 주장하지 않습니다. ", options: { color: INK } },
  { text: "설명할 수 있고, 고칠 수 있는 구조", options: { color: ACCENT } },
  { text: "를 주장합니다.", options: { color: INK } }
], {
  x: 0.45, y: 0.82, w: 12.4, h: 0.52, fontFace: KO, fontSize: 21, bold: true
});
s.addText("손해율 실적이 없으면 최적값은 계산할 수 없습니다. 그래서 값이 아니라 순서를 정하고, 그 순서가 흔들리지 않는지 969개 조합으로 확인했습니다.", {
  x: 0.45, y: 1.36, w: 12.4, h: 0.3, fontFace: KO, fontSize: 11.5, color: MUTED
});

// ── 3기둥 ──
const cols = [
  {
    x: 0.45, tag: "① 설명할 수 있는가",
    head: "규칙은 사람이 정하고,",
    head2: "판정은 고정 코드가 수행",
    body: "AI가 값을 고르는 방식은 왜 그 값인지 설명할 수 없습니다. 값 하나하나가 코드에 선언돼 있어 어느 판정이든 되짚어 재현·감사할 수 있습니다."
  },
  {
    x: 4.72, tag: "② 지금 최적인가 — 아닙니다",
    head: "값이 아니라",
    head2: "'순서'를 주장합니다",
    body: ""
  },
  {
    x: 8.99, tag: "③ 틀리면 고칠 수 있는가",
    head: "산식 구조는 그대로,",
    head2: "값만 재보정",
    body: "전 축이 선언 파라미터라, 파일럿 손해율이 쌓이면 그 목표로 재적합합니다. 아래 실측대로 값 근처에서 판정이 둔감해 재보정 리스크가 낮습니다."
  }
];
cols.forEach((c) => {
  s.addShape(pres.ShapeType.roundRect, {
    x: c.x, y: 1.84, w: 3.86, h: 2.26, fill: { color: CARD }, line: { color: CARD }, rectRadius: 0.08
  });
  s.addText(c.tag, {
    x: c.x + 0.22, y: 1.95, w: 3.45, h: 0.26, fontFace: KO, fontSize: 10.5, bold: true, color: ACCENT
  });
  s.addText(c.head, {
    x: c.x + 0.22, y: 2.25, w: 3.45, h: 0.3, fontFace: KO, fontSize: 14, bold: true, color: INK
  });
  s.addText(c.head2, {
    x: c.x + 0.22, y: 2.53, w: 3.45, h: 0.3, fontFace: KO, fontSize: 14, bold: true, color: INK
  });
  if (c.body) {
    s.addText(c.body, {
      x: c.x + 0.22, y: 2.94, w: 3.45, h: 1.0, fontFace: KO, fontSize: 10.5, color: BODY, lineSpacingMultiple: 1.3
    });
  }
});

// ② 기둥의 순서 표기 (별도 배치)
s.addText("노출 · 주 무대   ≫   보조 무대 · 변화", {
  x: 4.94, y: 2.96, w: 3.45, h: 0.28, fontFace: KO, fontSize: 12, bold: true, color: ACCENT
});
s.addText("주행거리 · 생활권 안   ≫   생활권 밖 · 패턴", {
  x: 4.94, y: 3.24, w: 3.45, h: 0.28, fontFace: KO, fontSize: 11, color: BODY
});
s.addText("정확히 30이어야 할 기준은 없습니다.", {
  x: 4.94, y: 3.62, w: 3.45, h: 0.28, fontFace: KO, fontSize: 10.5, color: MUTED
});

// ── 실측 헤더 ──
s.addText("실측 — 969개 가중치 조합 × 180 시나리오 재판정", {
  x: 0.45, y: 4.28, w: 7.0, h: 0.3, fontFace: KO, fontSize: 13, bold: true, color: INK
});
s.addText("판정을 좌우하는 축은 둘 — 현행 30은 두 축 모두에서 판정 변동이 가장 적은 지점", {
  x: 0.45, y: 4.57, w: 8.4, h: 0.26, fontFace: KO, fontSize: 10.5, color: MUTED
});

// ── 막대 차트 (도형으로 직접 — 뷰어 무관하게 렌더) ──
const LABELS = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50];
const MAXV = 35;
const PLOT_H = 1.28;

function drawChart(ox, title, note, data) {
  s.addText(title, {
    x: ox, y: 4.92, w: 2.3, h: 0.26, fontFace: KO, fontSize: 11.5, bold: true, color: INK
  });
  s.addText(note, {
    x: ox + 2.05, y: 4.94, w: 1.9, h: 0.24, fontFace: KO, fontSize: 9.5, bold: true, color: GOOD
  });
  const plotTop = 5.24;
  const plotBottom = plotTop + PLOT_H;
  // 기준선(가로)
  [0, 0.5, 1].forEach((f) => {
    s.addShape(pres.ShapeType.line, {
      x: ox, y: plotBottom - PLOT_H * f, w: 3.9, h: 0,
      line: { color: f === 0 ? "D5DAE4" : "EDF0F5", width: 0.75 }
    });
  });
  const step = 3.9 / LABELS.length;
  const bw = step * 0.62;
  data.forEach((v, i) => {
    const h = (v / MAXV) * PLOT_H;
    const bx = ox + step * i + (step - bw) / 2;
    const hi = LABELS[i] === 30;
    s.addShape(pres.ShapeType.rect, {
      x: bx, y: plotBottom - h, w: bw, h: h,
      fill: { color: hi ? BAR_HI : BAR }, line: { color: hi ? BAR_HI : BAR }
    });
    s.addText(String(LABELS[i]), {
      x: ox + step * i, y: plotBottom + 0.04, w: step, h: 0.2,
      fontFace: KO, fontSize: 8.5, color: hi ? ACCENT : MUTED, bold: hi, align: "center"
    });
    const isMax = v === Math.max.apply(null, data);
    if (hi || isMax) {
      s.addText(String(v), {
        x: bx - 0.18, y: plotBottom - h - 0.23, w: bw + 0.36, h: 0.2,
        fontFace: KO, fontSize: 9, bold: hi, color: hi ? ACCENT : "8A93A6", align: "center"
      });
    }
  });
  s.addText("가중치 값 →", {
    x: ox + 3.1, y: plotBottom + 0.26, w: 0.85, h: 0.18, fontFace: KO, fontSize: 8, color: "AEB6C4"
  });
}
drawChart(0.45, "주행거리 가중치", "진폭 27건 · 최저 30", [14.5, 13.3, 11.5, 9.4, 6.7, 5.4, 10.2, 22.3, 24.7, 32.6]);
drawChart(4.72, "생활권 안 안전 가중치", "진폭 22건 · 최저 30", [29.4, 26.0, 20.3, 14.0, 9.4, 7.4, 7.6, 8.5, 10.1, 13.0]);
s.addText("세로축 = 판정이 바뀐 시나리오 수 (180건 중)", {
  x: 0.45, y: 6.86, w: 4.5, h: 0.2, fontFace: KO, fontSize: 8, color: "AEB6C4"
});

// ── 비지배 축 카드 ──
s.addShape(pres.ShapeType.roundRect, {
  x: 8.99, y: 4.9, w: 3.86, h: 2.02, fill: { color: CARD }, line: { color: CARD }, rectRadius: 0.08
});
s.addText("나머지 두 축은 판정을 거의 움직이지 않습니다", {
  x: 9.21, y: 5.02, w: 3.45, h: 0.28, fontFace: KO, fontSize: 11.5, bold: true, color: INK
});
s.addText([
  { text: "생활권 밖 안전", options: { bold: true, color: INK } },
  { text: "   진폭 6건", options: { color: BODY } }
], { x: 9.21, y: 5.36, w: 3.45, h: 0.24, fontFace: KO, fontSize: 10.5 });
s.addText("어떤 값을 줘도 판정이 거의 그대로", {
  x: 9.21, y: 5.58, w: 3.45, h: 0.22, fontFace: KO, fontSize: 9.5, color: MUTED
});
s.addText([
  { text: "패턴 안정성", options: { bold: true, color: INK } },
  { text: "   진폭 10건", options: { color: BODY } }
], { x: 9.21, y: 5.82, w: 3.45, h: 0.24, fontFace: KO, fontSize: 10.5 });
s.addShape(pres.ShapeType.line, {
  x: 9.21, y: 6.06, w: 3.45, h: 0, line: { color: "DDE1EA", width: 1 }
});
s.addText("±5 이웃 19개 조합 — 판정 변경 중앙 3건 · 최대 9건", {
  x: 9.21, y: 6.2, w: 3.45, h: 0.24, fontFace: KO, fontSize: 10.5, bold: true, color: GOOD
});
s.addText("안정 구간(주행 ≤30 · 안 ≥25) 371개 — 중앙 11건", {
  x: 9.21, y: 6.44, w: 3.45, h: 0.24, fontFace: KO, fontSize: 10, color: BODY
});

// ── 각주 ──
s.addText("채택값 30/30/20/20 = 초기 설계값(prior) · 파일럿 손해율로 재적합   |   민감도는 합성 시나리오 기반 — 값의 정답이 아니라 판정의 둔감성을 보는 용도", {
  x: 0.45, y: 7.14, w: 12.4, h: 0.24, fontFace: KO, fontSize: 8.5, color: "9AA3B2"
});

s.addNotes("3단 서사: ① AI가 값을 고르면 설명 불가 → 규칙은 사람, 판정은 고정 코드 ② 손해율 없으면 최적값 계산 불가 → 값이 아니라 순서 ③ 전 축 선언 파라미터 → 구조 변경 없이 재보정. 차트는 ③의 근거(값 근처 둔감 = 재보정 안전). 969 조합 실측, rolling 번들 기준.");

pres.writeFile({ fileName: "/private/tmp/claude-501/-Users-gimdonghyeon-Desktop-seniorcareservice/60c72b2a-4eb8-48cb-9a78-503f6e83abe3/scratchpad/Appendix_C.pptx" })
  .then((f) => console.log("saved:", f));
