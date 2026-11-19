#!/usr/bin/env node
// Write one browser viewer per Markdown spec and link each ```mermaid block to its diagram in it.
// For <dir>/<stem>.md the viewer is <dir>/<stem>_images/<stem>.html; a link line follows each block's closing
// fence, and the blocks themselves stay as they are. Every diagram must parse first (validate_mermaid.mjs's
// parser); if any fails, nothing is written.
//
//   node render_diagrams.mjs <doc.md>...           writes the viewers and link lines; exits 1 on a parse failure
//   node render_diagrams.mjs --check <doc.md>...   writes nothing; exits 1 if a viewer or a link line is stale
//
// Exit 2 on a usage error. The viewer loads the pinned Mermaid from jsDelivr with a Subresource Integrity hash
// of the copy in validate_mermaid.mjs's shared cache, so its output is deterministic.
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { basename, dirname, extname, join } from "node:path";

import { MERMAID_BLOCK, PINS, cacheDir, checkFile, ensureDeps, loadParser, start } from "./validate_mermaid.mjs";

export const VIEWER_MARKER = "<!-- design-spec:viewer -->";

// Exactly the line insertLinks writes, so a user's own line that merely mentions the marker is never replaced.
const LINK_LINE = /^\[Open diagram in browser\]\([^\s()]*\) <!-- design-spec:viewer -->\r?\n?$/;

const USAGE = "usage: render_diagrams.mjs [--check] <doc.md>...\n";
const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
const STYLE = "body { font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 72rem; padding: 0 1rem; }\n"
    + "section { border-top: 1px solid #ccc; padding: 1rem 0; }\n"
    + "pre.mermaid { background: #fff; overflow-x: auto; }\n";
const RUN = "mermaid.initialize({ startOnLoad: false }); mermaid.run().then(() => { const target = location.hash && document.getElementById(location.hash.slice(1)); if (target) target.scrollIntoView(); });";

/** Return a heading as a URL fragment slug of at most 40 characters, or "diagram" when nothing is left. */
export function slugify(heading) {
    const slug = heading.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
    return slug.slice(0, 40).replace(/-+$/, "") || "diagram";
}

/** Return the anchor and viewer title of the number-th diagram (1-based) under the given heading text. */
export function diagramName(number, heading) {
    const nn = String(number).padStart(2, "0");
    return { anchor: `diagram-${nn}-${slugify(heading)}`, title: `${nn}. ${heading || "Diagram"}` };
}

/**
 * Return each line of text as { index, text, inside }: index is where the line starts, text has no line ending, and
 * inside is whether a ``` or ~~~ fence opened on an earlier line encloses it (its closing line included).
 */
export function scanLines(text) {
    const lines = [];
    let fence;
    let index = 0;
    for (const raw of text.split("\n")) {
        const line = raw.replace(/\r$/, "");
        const open = line.match(/^ {0,3}(`{3,}|~{3,})/);
        lines.push({ index, text: line, inside: fence !== undefined });
        if (fence) {
            fence = fence.test(line) ? undefined : fence;
        } else if (open) {
            fence = new RegExp(`^ {0,3}${open[1][0]}{${open[1].length},}[ \\t]*$`);
        }
        index += raw.length + 1;
    }
    return lines;
}

/** Return the ATX headings among scanned lines outside code fences as { index, text }. */
export function headings(lines) {
    const found = [];
    for (const line of lines.filter((each) => !each.inside)) {
        const heading = line.text.match(/^ {0,3}#{1,6}(?:[ \t]+(.*))?$/);
        if (heading) {
            found.push({ index: line.index, text: (heading[1] ?? "").replace(/(?:^|[ \t]+)#+[ \t]*$/, "").trim() });
        }
    }
    return found;
}

/** Return the link destination of a diagram in the viewer of stem, percent-encoded so Markdown reads it as one destination. */
export function linkDestination(stem, anchor) {
    const encoded = encodeURIComponent(stem).replace(/[()]/g, (character) => `%${character.charCodeAt(0).toString(16).toUpperCase()}`);
    return `${encoded}_images/${encoded}.html#${anchor}`;
}

/**
 * Return text with a viewer link on the line after the closing fence of each diagram, end being where its fence ends.
 * A generated link line already there is replaced; any other line is kept.
 */
export function insertLinks(text, stem, diagrams, eol) {
    let result = "";
    let from = 0;
    for (const { end, anchor } of diagrams) {
        const newline = text.indexOf("\n", end);
        const cut = newline === -1 ? text.length : newline + 1;
        const next = text.slice(cut).match(/^[^\n]*\n?/)[0];
        result += `${text.slice(from, cut)}${newline === -1 ? eol : ""}[Open diagram in browser](${linkDestination(stem, anchor)}) ${VIEWER_MARKER}${eol}`;
        from = LINK_LINE.test(next) ? cut + next.length : cut;
    }
    return result + text.slice(from);
}

/**
 * Return what rendering the spec at path with this text should produce: { stem, viewerPath, doc, diagrams }, where
 * doc is the linked document and each diagram is { anchor, title, source, end }. A Mermaid block inside an
 * enclosing fence is an example, not a diagram. Return null without diagrams.
 */
export function viewerPlan(path, text) {
    const lines = scanLines(text);
    const titles = headings(lines);
    const matches = [...text.matchAll(MERMAID_BLOCK)].filter((match) => !lines.findLast((line) => line.index <= match.index).inside);
    const diagrams = matches.map((match, index) => ({
        ...diagramName(index + 1, titles.findLast((heading) => heading.index < match.index)?.text ?? ""),
        source: match[1],
        end: match.index + match[0].length,
    }));
    if (diagrams.length === 0) {
        return null;
    }
    const stem = basename(path).slice(0, -extname(path).length);
    const doc = insertLinks(text, stem, diagrams, text.includes("\r\n") ? "\r\n" : "\n");
    return { stem, viewerPath: join(dirname(path), `${stem}_images`, `${stem}.html`), doc, diagrams };
}

function escapeHtml(text) {
    return text.replace(/[&<>"']/g, (character) => ESCAPES[character]);
}

/** Return the viewer HTML for a plan; integrity is the Subresource Integrity hash of the pinned mermaid.min.js. */
export function buildViewer(plan, integrity) {
    const sections = plan.diagrams.map(({ anchor, title, source }) => `<section id="${anchor}"><h2>${escapeHtml(title)}</h2><pre class="mermaid">${escapeHtml(source)}</pre></section>\n`);
    return [
        "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n",
        `<title>${escapeHtml(plan.stem)}.md diagrams</title>\n<style>\n${STYLE}</style>\n</head>\n<body>\n`,
        `<p>Generated by design-spec render_diagrams.mjs from ${escapeHtml(plan.stem)}.md. Do not edit; re-run the tool.</p>\n`,
        ...sections,
        `<script src="https://cdn.jsdelivr.net/npm/mermaid@${PINS.mermaid}/dist/mermaid.min.js" integrity="${integrity}" crossorigin="anonymous"></script>\n`,
        `<script>${RUN}</script>\n</body>\n</html>\n`,
    ].join("");
}

/** Return the Subresource Integrity hash of mermaid.min.js in the cache folder dir. */
export function integrityOf(dir) {
    return `sha384-${createHash("sha384").update(readFileSync(join(dir, "node_modules", "mermaid", "dist", "mermaid.min.js"))).digest("base64")}`;
}

/** Return why the file at path is not the expected content: "missing viewer file", "viewer differs", or undefined. */
function viewerProblem(path, expected) {
    if (!existsSync(path)) {
        return "missing viewer file";
    }
    return readFileSync(path, "utf8") === expected ? undefined : "viewer differs";
}

function staleReasons(plan, viewer, text) {
    return [viewerProblem(plan.viewerPath, viewer), text === plan.doc ? undefined : "link lines missing or wrong"].filter(Boolean);
}

/** Write the viewer and the document where they differ from the plan; return whether anything was written. */
function writePlan(path, plan, viewer, text) {
    const viewerStale = viewerProblem(plan.viewerPath, viewer) !== undefined;
    if (viewerStale) {
        mkdirSync(dirname(plan.viewerPath), { recursive: true });
        writeFileSync(plan.viewerPath, viewer);
    }
    if (text !== plan.doc) {
        writeFileSync(path, plan.doc);
    }
    return viewerStale || text !== plan.doc;
}

/** Run the CLI; io supplies out(text), err(text), getParse(), and getIntegrity(). Return the exit code. */
export async function main(argv, io) {
    const check = argv[0] === "--check";
    const paths = check ? argv.slice(1) : argv;
    if (paths.length === 0 || paths.some((path) => extname(path).toLowerCase() !== ".md")) {
        io.err(USAGE);
        return 2;
    }
    let parser;
    const getParse = async () => (parser ??= await io.getParse());
    const failures = [];
    for (const path of paths) {
        for (const result of (await checkFile(path, getParse)).filter((each) => !each.ok)) {
            failures.push(`${path}: block ${result.block} (line ${result.line}): FAIL ${result.detail}\n`);
        }
    }
    if (failures.length > 0) {
        io.out(failures.join(""));
        return 1;
    }
    let integrity;
    let stale = 0;
    for (const path of paths) {
        const text = readFileSync(path, "utf8");
        const plan = viewerPlan(path, text);
        if (plan === null) {
            io.out(`${path}: no Mermaid diagrams\n`);
            continue;
        }
        const viewer = buildViewer(plan, (integrity ??= io.getIntegrity()));
        if (check) {
            const reasons = staleReasons(plan, viewer, text);
            io.out(`${path}: viewer ${reasons.length === 0 ? "OK" : `STALE ${reasons.join("; ")}`}\n`);
            stale += reasons.length === 0 ? 0 : 1;
        } else {
            io.out(`${path}: viewer ${writePlan(path, plan, viewer, text) ? "written" : "up to date"}\n`);
        }
    }
    return stale === 0 ? 0 : 1;
}

const processIo = {
    out: (text) => process.stdout.write(text),
    err: (text) => process.stderr.write(text),
    getParse: () => loadParser(ensureDeps(cacheDir(process.env, homedir()))),
    getIntegrity: () => integrityOf(ensureDeps(cacheDir(process.env, homedir()))),
};
const exitCode = await start(import.meta.main, () => main(process.argv.slice(2), processIo), processIo, "render_diagrams.mjs");
if (exitCode !== undefined) {
    process.exitCode = exitCode;
}
