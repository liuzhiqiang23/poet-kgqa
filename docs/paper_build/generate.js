/* 论文 docx 生成器 — 按 docx skill 学术场景规范
 * 内容来自 content.json（ensure_ascii，规避引号转义问题）
 */
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  ImageRun, PageBreak, Header, Footer, NumberFormat, SimpleField,
  AlignmentType, HeadingLevel, WidthType, BorderStyle, ShadingType,
  SectionType, TableOfContents,
} = require("docx");
const fs = require("fs");
const path = require("path");

const C = JSON.parse(fs.readFileSync(path.join(__dirname, "content.json"), "utf-8"));
const META = C.meta;
const OUT = path.join(__dirname, "毕设论文-融合知识图谱与大语言模型的诗人知识问答与对话系统设计.docx");

const NB = { style: BorderStyle.NONE, size: 0, color: "auto" };
const FONT_BODY = { ascii: "Times New Roman", eastAsia: "SimSun" };
const FONT_HEAD = { ascii: "Times New Roman", eastAsia: "SimHei" };

function safeText(v, fb) { return (v && String(v).trim()) ? String(v).trim() : fb; }

/* ---------- 块渲染 ---------- */
function parseBold(text) {
  // **bold** 拆分
  const parts = [];
  let rest = text;
  while (true) {
    const i = rest.indexOf("**");
    if (i < 0) { parts.push({ text: rest, bold: false }); break; }
    const j = rest.indexOf("**", i + 2);
    if (j < 0) { parts.push({ text: rest, bold: false }); break; }
    if (i > 0) parts.push({ text: rest.slice(0, i), bold: false });
    parts.push({ text: rest.slice(i + 2, j), bold: true });
    rest = rest.slice(j + 2);
  }
  return parts.filter(p => p.text.length);
}

function bodyPara(text, opts = {}) {
  const runs = parseBold(text).map(p => new TextRun({
    text: p.text, bold: p.bold, size: 24, color: "000000", font: FONT_BODY,
  }));
  return new Paragraph({
    alignment: AlignmentType.JUSTIFIED,
    indent: opts.noIndent ? undefined : { firstLine: 480 },
    spacing: { line: 360 },
    children: runs,
  });
}

function liPara(text) {
  return new Paragraph({
    alignment: AlignmentType.JUSTIFIED,
    bullet: { level: 0 },
    spacing: { line: 360 },
    children: parseBold(text).map(p => new TextRun({
      text: p.text, bold: p.bold, size: 24, color: "000000", font: FONT_BODY })),
  });
}

function heading(level, text) {
  const map = { 1: HeadingLevel.HEADING_1, 2: HeadingLevel.HEADING_2, 3: HeadingLevel.HEADING_3 };
  return new Paragraph({
    heading: map[level],
    children: [new TextRun({ text, bold: true, color: "000000",
      size: level === 1 ? 32 : (level === 2 ? 30 : 28), font: FONT_HEAD })],
  });
}

function threeLineTable(rows) {
  const header = rows[0], data = rows.slice(1);
  const nCols = header.length;
  return new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    borders: {
      top: { style: BorderStyle.SINGLE, size: 6, color: "000000" },
      bottom: { style: BorderStyle.SINGLE, size: 6, color: "000000" },
      left: NB, right: NB, insideHorizontal: NB, insideVertical: NB,
    },
    rows: [
      new TableRow({
        tableHeader: true, cantSplit: true,
        children: header.map(text => new TableCell({
          borders: { bottom: { style: BorderStyle.SINGLE, size: 3, color: "000000" }, top: NB, left: NB, right: NB },
          margins: { top: 60, bottom: 60, left: 100, right: 100 },
          children: [new Paragraph({ alignment: AlignmentType.CENTER, spacing: { line: 300 },
            children: [new TextRun({ text, bold: true, size: 21, font: FONT_BODY })] })],
        })),
      }),
      ...data.map((r, ri) => new TableRow({
        cantSplit: true,
        children: r.map(text => new TableCell({
          borders: (ri === data.length - 1) ? { top: NB, left: NB, right: NB, bottom: NB } : { top: NB, left: NB, right: NB, bottom: NB },
          margins: { top: 50, bottom: 50, left: 100, right: 100 },
          children: [new Paragraph({ alignment: AlignmentType.CENTER, spacing: { line: 300 },
            children: [new TextRun({ text, size: 21, font: FONT_BODY })] })],
        })),
      })),
    ],
  });
}

function pngSize(buf) { return { w: buf.readUInt32BE(16), h: buf.readUInt32BE(20) }; }

function imageBlock(block) {
  const p = path.join(__dirname, block.path);
  const buf = fs.readFileSync(p);
  const { w, h } = pngSize(buf);
  const displayWidth = 520;
  const displayHeight = Math.round(displayWidth * h / w);
  return [
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120, line: 240 },
      children: [new ImageRun({ data: buf, transformation: { width: displayWidth, height: displayHeight }, type: "png" })] }),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 60, after: 200, line: 240 },
      children: [new TextRun({ text: block.caption, size: 21, font: FONT_BODY })] }),
  ];
}

function algBlock(block) {
  const mk = (text, opts = {}) => new Paragraph({
    alignment: AlignmentType.LEFT,
    indent: { left: 480 },
    spacing: { line: 280 },
    children: [new TextRun({ text, size: 21, bold: !!opts.bold, font: FONT_BODY })],
  });
  return [
    mk(block.caption, { bold: true }),
    ...block.lines.map(l => mk(l)),
    new Paragraph({ spacing: { after: 120 }, children: [] }),
  ];
}

function renderBlocks(blocks) {
  const out = [];
  for (const b of blocks) {
    if (b.type === "h1") out.push(heading(1, b.text));
    else if (b.type === "h2") out.push(heading(2, b.text));
    else if (b.type === "h3") out.push(heading(3, b.text));
    else if (b.type === "p") {
      if (/^\*\*关键词|^Keywords/i.test(b.text)) out.push(bodyPara(b.text, { noIndent: true }));
      else out.push(bodyPara(b.text));
    }
    else if (b.type === "li") out.push(liPara(b.text));
    else if (b.type === "tbltitle") out.push(new Paragraph({
      keepNext: true, alignment: AlignmentType.CENTER, spacing: { before: 160, after: 80, line: 240 },
      children: [new TextRun({ text: b.text, size: 21, font: FONT_BODY })] }));
    else if (b.type === "table") out.push(threeLineTable(b.rows), new Paragraph({ spacing: { after: 120 }, children: [] }));
    else if (b.type === "image") out.push(...imageBlock(b));
    else if (b.type === "alg") out.push(...algBlock(b));
  }
  return out;
}

/* ---------- 页眉页脚 ---------- */
function buildHeader() {
  return new Header({ children: [new Paragraph({
    alignment: AlignmentType.CENTER,
    border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: "000000" } },
    children: [new TextRun({ text: safeText(META.header, "毕业论文"), size: 18, color: "333333", font: FONT_BODY })],
  })] });
}
function footerWith(fmt) {
  const field = fmt === "roman" ? "PAGE \\* ROMAN \\* MERGEFORMAT" : "PAGE \\* arabic \\* MERGEFORMAT";
  return new Footer({ children: [new Paragraph({
    alignment: AlignmentType.CENTER,
    children: [
      new TextRun({ text: "- ", size: 21, font: FONT_BODY }),
      new SimpleField(field),
      new TextRun({ text: " -", size: 21, font: FONT_BODY }),
    ],
  })] });
}

/* ---------- 封面（学术场景 buildAcademicCover 适配） ---------- */
function buildAcademicCover() {
  const infoRows = [
    ["学　　院", safeText(META.college, "【学院】")],
    ["专　　业", safeText(META.major, "【专业】")],
    ["学生姓名", safeText(META.author, "【姓名】")],
    ["学　　号", safeText(META.student_id, "【学号】")],
    ["指导教师", safeText(META.advisor, "【指导教师】")],
  ];
  const infoTable = new Table({
    width: { size: 62, type: WidthType.PERCENTAGE },
    alignment: AlignmentType.CENTER,
    borders: { top: NB, bottom: NB, left: NB, right: NB, insideHorizontal: NB, insideVertical: NB },
    rows: infoRows.map(([label, value]) => new TableRow({
      cantSplit: true,
      children: [
        new TableCell({
          width: { size: 35, type: WidthType.PERCENTAGE },
          borders: { bottom: NB, top: NB, left: NB, right: NB },
          margins: { top: 60, bottom: 60, left: 120, right: 120 },
          children: [new Paragraph({ alignment: AlignmentType.RIGHT, spacing: { line: Math.ceil(14 * 23), lineRule: "atLeast" },
            children: [new TextRun({ text: label + "：", size: 28, font: FONT_HEAD })] })],
        }),
        new TableCell({
          borders: { bottom: { style: BorderStyle.SINGLE, size: 4, color: "000000" }, top: NB, left: NB, right: NB },
          margins: { top: 60, bottom: 60, left: 120, right: 120 },
          children: [new Paragraph({ alignment: AlignmentType.CENTER, spacing: { line: Math.ceil(14 * 23), lineRule: "atLeast" },
            children: [new TextRun({ text: value, size: 28, font: FONT_BODY })] })],
        }),
      ],
    })),
  });
  return [
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 1200, after: 300, line: Math.ceil(22 * 23), lineRule: "atLeast" },
      children: [new TextRun({ text: safeText(META.school, "【学校名称】"), size: 44, bold: true, font: FONT_HEAD })] }),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 700, line: Math.ceil(18 * 23), lineRule: "atLeast" },
      children: [new TextRun({ text: "本科毕业论文（设计）", size: 36, font: FONT_HEAD })] }),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 160, line: Math.ceil(18 * 23), lineRule: "atLeast" },
      children: [new TextRun({ text: safeText(META.title, "【论文题目】"), size: 36, bold: true, font: FONT_HEAD })] }),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 900, line: Math.ceil(16 * 23), lineRule: "atLeast" },
      children: [new TextRun({ text: safeText(META.title_en, ""), size: 28, font: FONT_BODY })] }),
    infoTable,
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 1100, line: Math.ceil(14 * 23), lineRule: "atLeast" },
      children: [new TextRun({ text: safeText(META.date, "2026年10月"), size: 28, font: FONT_BODY })] }),
  ];
}

/* ---------- 分节 ---------- */
const PAGE = {
  size: { width: 11906, height: 16838 },
  margin: { top: 1440, bottom: 1440, left: 1701, right: 1417, header: 850, footer: 992 },
};

const abstractCN = renderBlocks(C.sections.ABSTRACT_CN || []);
const abstractEN = renderBlocks(C.sections.ABSTRACT_EN || []);
const appendix = renderBlocks(C.sections.APPENDIX || []);
const ack = renderBlocks(C.sections.ACKNOWLEDGEMENTS || []);

// BODY 按 "参考文献" h1 切分
const bodyBlocks = C.sections.BODY || [];
const refIdx = bodyBlocks.findIndex(b => b.type === "h1" && b.text === "参考文献");
const mainBlocks = refIdx >= 0 ? bodyBlocks.slice(0, refIdx) : bodyBlocks;
const refBlocks = refIdx >= 0 ? bodyBlocks.slice(refIdx) : [];
const bodyChildren = renderBlocks(mainBlocks);

const refChildren = [heading(1, "参考文献")];
for (const b of refBlocks) {
  if (b.type === "p" && /^\[\d+\]/.test(b.text)) {
    refChildren.push(new Paragraph({
      indent: { left: 420, hanging: 420 },
      spacing: { line: 360 },
      children: [new TextRun({ text: b.text, size: 21, font: FONT_BODY })],
    }));
  }
}

const tocSection = {
  properties: { type: SectionType.NEXT_PAGE, page: { ...PAGE, pageNumbers: { formatType: NumberFormat.UPPER_ROMAN } } },
  headers: { default: buildHeader() },
  footers: { default: footerWith("roman") },
  children: [
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 240, after: 240, line: 360 },
      children: [new TextRun({ text: "目　　录", bold: true, size: 32, font: FONT_HEAD })] }),
    new TableOfContents("目录", { hyperlink: true, headingStyleRange: "1-3" }),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 200, line: 300 },
      children: [new TextRun({ text: "（在 Word 中右键目录并选择\u201c更新域\u201d以刷新页码）", italics: true, size: 18, color: "888888", font: FONT_BODY })] }),
  ],
};

const doc = new Document({
  creator: safeText(META.author, "author"),
  title: safeText(META.title, "thesis"),
  features: { updateFields: true },
  styles: {
    default: {
      document: {
        run: { font: FONT_BODY, size: 24, color: "000000" },
        paragraph: { spacing: { line: 360 } },
      },
      heading1: {
        run: { font: FONT_HEAD, size: 32, bold: true, color: "000000" },
        paragraph: { alignment: AlignmentType.CENTER, spacing: { before: 480, after: 360, line: 360 } },
      },
      heading2: {
        run: { font: FONT_HEAD, size: 30, bold: true, color: "000000" },
        paragraph: { spacing: { before: 360, after: 240, line: 360 } },
      },
      heading3: {
        run: { font: FONT_HEAD, size: 28, bold: true, color: "000000" },
        paragraph: { spacing: { before: 240, after: 120, line: 360 } },
      },
    },
  },
  sections: [
    { properties: { page: { size: PAGE.size, margin: { top: 0, bottom: 0, left: 0, right: 0 } }, titlePage: true },
      children: buildAcademicCover() },
    { properties: { type: SectionType.NEXT_PAGE, page: { ...PAGE, pageNumbers: { start: 1, formatType: NumberFormat.UPPER_ROMAN } } },
      headers: { default: buildHeader() }, footers: { default: footerWith("roman") }, children: abstractCN },
    { properties: { type: SectionType.NEXT_PAGE, page: { ...PAGE, pageNumbers: { formatType: NumberFormat.UPPER_ROMAN } } },
      headers: { default: buildHeader() }, footers: { default: footerWith("roman") }, children: abstractEN },
    tocSection,
    { properties: { type: SectionType.NEXT_PAGE, page: { ...PAGE, pageNumbers: { start: 1, formatType: NumberFormat.DECIMAL } } },
      headers: { default: buildHeader() }, footers: { default: footerWith("arabic") }, children: bodyChildren },
    { properties: { type: SectionType.NEXT_PAGE, page: { ...PAGE, pageNumbers: { formatType: NumberFormat.DECIMAL } } },
      headers: { default: buildHeader() }, footers: { default: footerWith("arabic") }, children: refChildren },
    { properties: { type: SectionType.NEXT_PAGE, page: { ...PAGE, pageNumbers: { formatType: NumberFormat.DECIMAL } } },
      headers: { default: buildHeader() }, footers: { default: footerWith("arabic") }, children: appendix },
    { properties: { type: SectionType.NEXT_PAGE, page: { ...PAGE, pageNumbers: { formatType: NumberFormat.DECIMAL } } },
      headers: { default: buildHeader() }, footers: { default: footerWith("arabic") }, children: ack },
  ],
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync(OUT, buf);
  console.log("written:", OUT, (buf.length / 1024).toFixed(0) + "KB");
});
