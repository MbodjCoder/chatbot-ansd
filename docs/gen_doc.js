/* Document scientifique de présentation du mémoire — RAMA-ANSD */
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle,
  ImageRun, PageBreak, TableOfContents, LevelFormat, PageNumber, Footer, Header,
} = require("docx");

const ENCRE = "12263A", VERT = "0E7C5B", GRISF = "33475C", LIGNE = "DBE3EA", FOND = "EEF2F5";

const p = (text, opts = {}) => new Paragraph({
  alignment: AlignmentType.JUSTIFIED,
  spacing: { after: 140, line: 300 },
  ...opts.para,
  children: [new TextRun({ text, size: 21, font: "Calibri", color: "222222", ...opts.run })],
});
const rich = (runs, opts = {}) => new Paragraph({
  alignment: AlignmentType.JUSTIFIED, spacing: { after: 140, line: 300 }, ...opts,
  children: runs.map(r => new TextRun({ size: 21, font: "Calibri", color: "222222", ...r })),
});
const h1 = t => new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { before: 300, after: 160 }, children: [new TextRun({ text: t, size: 30, bold: true, color: ENCRE, font: "Calibri" })] });
const h2 = t => new Paragraph({ heading: HeadingLevel.HEADING_2, spacing: { before: 220, after: 120 }, children: [new TextRun({ text: t, size: 24, bold: true, color: VERT, font: "Calibri" })] });
const bullet = (t, runs) => new Paragraph({
  numbering: { reference: "puces", level: 0 }, spacing: { after: 80, line: 290 },
  children: (runs || [{ text: t }]).map(r => new TextRun({ size: 21, font: "Calibri", ...r })),
});

const cell = (text, { bold = false, fill = null, w, color = "222222", size = 18 } = {}) =>
  new TableCell({
    width: { size: w, type: WidthType.DXA },
    shading: fill ? { type: ShadingType.CLEAR, fill } : undefined,
    margins: { top: 70, bottom: 70, left: 110, right: 110 },
    children: [new Paragraph({ spacing: { after: 0, line: 250 },
      children: [new TextRun({ text, bold, size, color, font: "Calibri" })] })],
  });

function table(headers, rows, widths) {
  const total = widths.reduce((a, b) => a + b, 0);
  return new Table({
    width: { size: total, type: WidthType.DXA }, columnWidths: widths,
    borders: {
      top: { style: BorderStyle.SINGLE, size: 4, color: LIGNE }, bottom: { style: BorderStyle.SINGLE, size: 4, color: LIGNE },
      left: { style: BorderStyle.SINGLE, size: 4, color: LIGNE }, right: { style: BorderStyle.SINGLE, size: 4, color: LIGNE },
      insideHorizontal: { style: BorderStyle.SINGLE, size: 4, color: LIGNE },
      insideVertical: { style: BorderStyle.SINGLE, size: 4, color: LIGNE },
    },
    rows: [
      new TableRow({ tableHeader: true, children: headers.map((h, i) => cell(h, { bold: true, fill: ENCRE, color: "FFFFFF", w: widths[i] })) }),
      ...rows.map((r, ri) => new TableRow({
        children: r.map((c, i) => cell(String(c), { w: widths[i], fill: ri % 2 ? FOND : null })),
      })),
    ],
  });
}

const espace = () => new Paragraph({ spacing: { after: 120 }, children: [] });
const saut = () => new Paragraph({ children: [new PageBreak()] });

/* ------------------------------------------------------------------ garde */
const garde = [
  new Paragraph({ spacing: { before: 1400 }, alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: "MÉMOIRE DE MASTER EN INFORMATIQUE", size: 26, bold: true, color: GRISF, font: "Calibri" })] }),
  new Paragraph({ spacing: { before: 500, after: 200 }, alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: "RAMA-ANSD", size: 64, bold: true, color: ENCRE, font: "Calibri" })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 400 },
    children: [new TextRun({ text: "Conception, implémentation et évaluation d'un chatbot intelligent pour le site web de l'Agence Nationale de la Statistique et de la Démographie : une architecture hybride fiable combinant Retrieval-Augmented Generation et Text-to-SQL", size: 27, color: ENCRE, italics: true, font: "Calibri" })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 },
    children: [new TextRun({ text: "Document scientifique de présentation du sujet", size: 23, bold: true, color: VERT, font: "Calibri" })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 900, after: 60 },
    children: [new TextRun({ text: "Auteur : Mbodj — Master Informatique", size: 22, font: "Calibri" })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 60 },
    children: [new TextRun({ text: "Université Gaston Berger — Année académique 2025-2026", size: 22, font: "Calibri" })] }),
  new Paragraph({ alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: "Directeur de mémoire : [à compléter]", size: 22, color: GRISF, font: "Calibri" })] }),
  saut(),
];

/* ------------------------------------------------------------------ TOC */
const _sommaire = [
  "1. Contexte institutionnel et problématique",
  "2. Objectifs de l'étude",
  "3. État de l'art synthétique",
  "4. Lacunes scientifiques, questions de recherche et hypothèses",
  "5. Architecture proposée : RAMA-ANSD",
  "6. Matrice de justification des choix techniques",
  "7. Méthodologie et protocole d'évaluation",
  "8. Prototype réalisé et résultats préliminaires",
  "9. Contributions attendues et plan de travail",
  "10. Références bibliographiques",
];
const toc = [
  h1("Sommaire"),
  ..._sommaire.map(t => new Paragraph({
    spacing: { after: 170, line: 300 }, indent: { left: 240 },
    children: [new TextRun({ text: t, size: 23, color: ENCRE, font: "Calibri" })],
  })),
  saut(),
];

module.exports = { p, rich, h1, h2, bullet, table, espace, saut, garde, toc,
  Document, Packer, Paragraph, TextRun, ImageRun, AlignmentType, LevelFormat,
  Footer, Header, PageNumber, ENCRE, VERT, GRISF };
