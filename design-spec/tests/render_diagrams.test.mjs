// Tests for skill/tools/render_diagrams.mjs. Run from the repository root:
//   node --test --experimental-test-coverage --test-coverage-include="design-spec/skill/tools/*.mjs" \
//     --test-coverage-lines=100 --test-coverage-branches=100 "design-spec/tests/*.test.mjs"
// The parser and the integrity hash are ports, so these tests inject fakes for both.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, describe, test } from "node:test";
import { fileURLToPath } from "node:url";

import {
    VIEWER_MARKER,
    buildViewer,
    diagramName,
    headings,
    insertLinks,
    integrityOf,
    linkDestination,
    main,
    scanLines,
    slugify,
    viewerPlan,
} from "../skill/tools/render_diagrams.mjs";
import { PINS } from "../skill/tools/validate_mermaid.mjs";

const SCRIPT = fileURLToPath(new URL("../skill/tools/render_diagrams.mjs", import.meta.url));
const GOOD = "flowchart LR\n    A --> B\n";
const BAD = "flowchart LR\n    A --> (\n";
const DOC = "# Spec\n\n## Context view\n\n```mermaid\n" + GOOD + "```\n\ntext\n\n## States\n\n```mermaid\nstateDiagram-v2\n    [*] --> A\n```\n";
const work = mkdtempSync(join(tmpdir(), "render-diagrams-"));
after(() => rmSync(work, { recursive: true, force: true }));

function spec(name, text) {
    const dir = mkdtempSync(join(work, "doc-"));
    const path = join(dir, name);
    writeFileSync(path, text);
    return path;
}

function capture() {
    const io = { outText: "", errText: "", parses: 0, hashes: 0 };
    io.out = (text) => { io.outText += text; };
    io.err = (text) => { io.errText += text; };
    io.getParse = async () => {
        io.parses += 1;
        return async (source) => (source.includes("(") ? { ok: false, detail: "Parse error on line 2" } : { ok: true, detail: "flowchart-v2" });
    };
    io.getIntegrity = () => {
        io.hashes += 1;
        return "sha384-fake";
    };
    return io;
}

describe("slugify", () => {
    test("lowercases and joins runs of other characters with one hyphen", () => {
        assert.equal(slugify("Context view: the System (v2)"), "context-view-the-system-v2");
    });

    test("trims hyphens at both ends", () => {
        assert.equal(slugify("  --Data flow!-- "), "data-flow");
    });

    test("cuts to 40 characters without leaving a trailing hyphen", () => {
        assert.equal(slugify("a".repeat(39) + " bcd"), "a".repeat(39));
        assert.equal(slugify("b".repeat(50)), "b".repeat(40));
    });

    test("falls back to diagram when nothing is left", () => {
        assert.equal(slugify(""), "diagram");
        assert.equal(slugify("Überblick ★"), "berblick");
        assert.equal(slugify("★ ★"), "diagram");
    });
});

describe("diagramName", () => {
    test("numbers the anchor and title with two digits from 1", () => {
        assert.deepEqual(diagramName(3, "Context view"), { anchor: "diagram-03-context-view", title: "03. Context view" });
        assert.deepEqual(diagramName(12, "x"), { anchor: "diagram-12-x", title: "12. x" });
    });

    test("names a diagram without a heading Diagram", () => {
        assert.deepEqual(diagramName(1, ""), { anchor: "diagram-01-diagram", title: "01. Diagram" });
    });
});

describe("scanLines", () => {
    test("returns each line's offset and text without CR, and whether an earlier line's fence encloses it", () => {
        assert.deepEqual(scanLines("a\r\n````md\n```\nx\n````\nb"), [
            { index: 0, text: "a", inside: false },
            { index: 3, text: "````md", inside: false },
            { index: 10, text: "```", inside: true },
            { index: 14, text: "x", inside: true },
            { index: 16, text: "````", inside: true },
            { index: 21, text: "b", inside: false },
        ]);
    });

    test("closes a tilde fence only with tildes", () => {
        assert.deepEqual(scanLines("~~~\n```\n~~~\nz\n").map((line) => line.inside), [false, true, true, false, false]);
    });
});

describe("headings", () => {
    test("returns each ATX heading's text and the offset of its line", () => {
        assert.deepEqual(headings(scanLines("# One\ntext\n  ## Two ##\r\n###\n")), [
            { index: 0, text: "One" },
            { index: 11, text: "Two" },
            { index: 24, text: "" },
        ]);
    });

    test("ignores lines that are not headings", () => {
        assert.deepEqual(headings(scanLines("#hashtag\n####### seven\n    # indented code\n")), []);
    });

    test("ignores headings inside backtick and tilde fences until a long enough closing fence", () => {
        const text = "````\n# in\n```\n# still in\n````\n~~~ python\n# tilde\n~~~\n# Out\n";
        assert.deepEqual(headings(scanLines(text)).map((h) => h.text), ["Out"]);
    });
});

describe("linkDestination", () => {
    test("percent-encodes the stem so it stays one Markdown link destination", () => {
        assert.equal(linkDestination("my spec", "diagram-01-x"), "my%20spec_images/my%20spec.html#diagram-01-x");
        assert.equal(linkDestination("design#2", "a"), "design%232_images/design%232.html#a");
        assert.equal(linkDestination("a)b(c", "a"), "a%29b%28c_images/a%29b%28c.html#a");
    });
});

describe("insertLinks", () => {
    const diagram = (end, anchor) => ({ end, anchor });

    test("puts the link on the line after each closing fence", () => {
        const text = "```mermaid\nA\n```\nafter\n";
        assert.equal(insertLinks(text, "my spec", [diagram(16, "diagram-01-x")], "\n"),
            `\`\`\`mermaid\nA\n\`\`\`\n[Open diagram in browser](my%20spec_images/my%20spec.html#diagram-01-x) ${VIEWER_MARKER}\nafter\n`);
    });

    test("ends a closing fence at end of file with a newline before the link", () => {
        assert.equal(insertLinks("```mermaid\nA\n```", "d", [diagram(16, "a")], "\r\n"),
            `\`\`\`mermaid\nA\n\`\`\`\r\n[Open diagram in browser](d_images/d.html#a) ${VIEWER_MARKER}\r\n`);
    });

    test("replaces a generated link line directly after the closing fence, with or without CR or a final newline", () => {
        const link = `[Open diagram in browser](d_images/d.html#a) ${VIEWER_MARKER}`;
        for (const old of [`[Open diagram in browser](old_images/old.html#x) ${VIEWER_MARKER}\n`, `[Open diagram in browser](x) ${VIEWER_MARKER}\r\n`, `[Open diagram in browser](x) ${VIEWER_MARKER}`]) {
            assert.equal(insertLinks("```mermaid\nA\n```\n" + old, "d", [diagram(16, "a")], "\n"), "```mermaid\nA\n```\n" + link + "\n");
        }
    });

    test("keeps a line after the fence that is not exactly a generated link", () => {
        const link = `[Open diagram in browser](d_images/d.html#a) ${VIEWER_MARKER}\n`;
        for (const kept of [`Keep this ${VIEWER_MARKER}\n`, `[Open diagram in browser](x) ${VIEWER_MARKER} \n`, `[Open diagram in browser](a b) ${VIEWER_MARKER}\n`]) {
            assert.equal(insertLinks("```mermaid\nA\n```\n" + kept, "d", [diagram(16, "a")], "\n"), "```mermaid\nA\n```\n" + link + kept);
        }
    });
});

describe("viewerPlan", () => {
    test("returns null for a document without Mermaid diagrams", () => {
        assert.equal(viewerPlan("plain.md", "# Title\n\n```python\nx = 1\n```\n"), null);
        assert.equal(viewerPlan("empty.md", ""), null);
    });

    test("names each diagram after the nearest heading before it and links it to the viewer", () => {
        const plan = viewerPlan(join("docs", "design.md"), DOC);
        assert.equal(plan.stem, "design");
        assert.equal(plan.viewerPath, join("docs", "design_images", "design.html"));
        assert.deepEqual(plan.diagrams.map((d) => [d.anchor, d.title, d.source]), [
            ["diagram-01-context-view", "01. Context view", GOOD],
            ["diagram-02-states", "02. States", "stateDiagram-v2\n    [*] --> A\n"],
        ]);
        assert.equal(plan.doc, DOC
            .replace("```\n\ntext", `\`\`\`\n[Open diagram in browser](design_images/design.html#diagram-01-context-view) ${VIEWER_MARKER}\n\ntext`)
            .replace(/```\n$/, `\`\`\`\n[Open diagram in browser](design_images/design.html#diagram-02-states) ${VIEWER_MARKER}\n`));
    });

    test("names a diagram before any heading, and skips headings inside fences", () => {
        const plan = viewerPlan("a.MD", "```mermaid\n" + GOOD + "```\n```text\n# Not a heading\n```\n```mermaid\n" + GOOD + "```\n");
        assert.equal(plan.stem, "a");
        assert.deepEqual(plan.diagrams.map((d) => d.anchor), ["diagram-01-diagram", "diagram-02-diagram"]);
    });

    test("is idempotent: planning its own output gives the same document", () => {
        const once = viewerPlan("design.md", DOC).doc;
        assert.equal(viewerPlan("design.md", once).doc, once);
    });

    test("leaves marker lines that are not the generated link after a closing fence alone", () => {
        const text = "# T\nKeep this <!-- design-spec:viewer -->\n```mermaid\nflowchart LR\n A-->B\n```\n";
        assert.equal(viewerPlan("d.md", text).doc, text + `[Open diagram in browser](d_images/d.html#diagram-01-t) ${VIEWER_MARKER}\n`);
        const elsewhere = `[Open diagram in browser](old.html#x) ${VIEWER_MARKER}\n\n\`\`\`text\n[Open diagram in browser](x) ${VIEWER_MARKER}\n\`\`\`\n`;
        const doc = viewerPlan("d.md", elsewhere + "```mermaid\n" + GOOD + "```\n").doc;
        assert.ok(doc.startsWith(elsewhere));
    });

    test("replaces the link line after each block, so a stale anchor is corrected", () => {
        const stale = viewerPlan("design.md", DOC).doc.replace("diagram-01-context-view", "diagram-01-old");
        assert.equal(viewerPlan("design.md", stale).doc, viewerPlan("design.md", DOC).doc);
    });

    test("skips a Mermaid example inside an enclosing backtick or tilde fence", () => {
        for (const [open, close] of [["````markdown", "````"], ["~~~", "~~~"]]) {
            const example = `# Example\n${open}\n\`\`\`mermaid\n${GOOD}\`\`\`\n${close}\n`;
            assert.equal(viewerPlan("d.md", example), null);
            const plan = viewerPlan("d.md", example + "## Real\n```mermaid\n" + GOOD + "```\n");
            assert.deepEqual(plan.diagrams.map((d) => d.anchor), ["diagram-01-real"]);
            assert.ok(plan.doc.startsWith(example));
        }
    });

    test("links a stem with # or parentheses as a single destination", () => {
        const text = "```mermaid\n" + GOOD + "```\n";
        assert.equal(viewerPlan("design#2.md", text).doc, text + `[Open diagram in browser](design%232_images/design%232.html#diagram-01-diagram) ${VIEWER_MARKER}\n`);
        assert.equal(viewerPlan("a)b.md", text).doc, text + `[Open diagram in browser](a%29b_images/a%29b.html#diagram-01-diagram) ${VIEWER_MARKER}\n`);
        assert.equal(viewerPlan(join("docs", "a)b.md"), text).viewerPath, join("docs", "a)b_images", "a)b.html"));
    });

    test("keeps CRLF line endings, including on the inserted lines", () => {
        const doc = viewerPlan("design.md", DOC.replaceAll("\n", "\r\n")).doc;
        assert.equal(doc, viewerPlan("design.md", DOC).doc.replaceAll("\n", "\r\n"));
    });

    test("handles a closing fence at end of file without a trailing newline", () => {
        const doc = viewerPlan("design.md", "## End\n```mermaid\n" + GOOD + "```").doc;
        assert.equal(doc, "## End\n```mermaid\n" + GOOD + `\`\`\`\n[Open diagram in browser](design_images/design.html#diagram-01-end) ${VIEWER_MARKER}\n`);
        assert.equal(viewerPlan("design.md", doc).doc, doc);
    });
});

describe("buildViewer", () => {
    const plan = { stem: "design", diagrams: [{ anchor: "diagram-01-a-b", title: "01. A & <B>", source: 'flowchart LR\n    A["x & \'y\'"] --> B<br>\n' }] };

    test("escapes the heading and the diagram source", () => {
        const html = buildViewer(plan, "sha384-abc");
        assert.match(html, /<section id="diagram-01-a-b"><h2>01\. A &amp; &lt;B&gt;<\/h2><pre class="mermaid">flowchart LR\n {4}A\[&quot;x &amp; &#39;y&#39;&quot;\] --&gt; B&lt;br&gt;\n<\/pre><\/section>/);
    });

    test("loads the pinned Mermaid with its integrity and scrolls to the hash after rendering", () => {
        const html = buildViewer(plan, "sha384-abc");
        assert.ok(html.startsWith("<!doctype html>\n"));
        assert.match(html, /<meta charset="utf-8">/);
        assert.match(html, /<title>design\.md diagrams<\/title>/);
        assert.match(html, /Generated by design-spec render_diagrams\.mjs from design\.md\. Do not edit; re-run the tool\./);
        assert.ok(html.includes(`<script src="https://cdn.jsdelivr.net/npm/mermaid@${PINS.mermaid}/dist/mermaid.min.js" integrity="sha384-abc" crossorigin="anonymous"></script>`));
        assert.ok(html.includes("mermaid.initialize({ startOnLoad: false }); mermaid.run().then(() => { const target = location.hash && document.getElementById(location.hash.slice(1)); if (target) target.scrollIntoView(); });"));
    });

    test("is deterministic", () => {
        assert.equal(buildViewer(plan, "sha384-abc"), buildViewer(structuredClone(plan), "sha384-abc"));
    });
});

describe("integrityOf", () => {
    test("hashes the cached mermaid.min.js with SHA-384", () => {
        const dir = mkdtempSync(join(work, "cache-"));
        mkdirSync(join(dir, "node_modules", "mermaid", "dist"), { recursive: true });
        writeFileSync(join(dir, "node_modules", "mermaid", "dist", "mermaid.min.js"), "window.mermaid = {};\n");
        const expected = `sha384-${createHash("sha384").update("window.mermaid = {};\n").digest("base64")}`;
        assert.equal(integrityOf(dir), expected);
    });
});

describe("main", () => {
    test("prints usage and exits 2 without files, including after --check", async () => {
        for (const argv of [[], ["--check"]]) {
            const io = capture();
            assert.equal(await main(argv, io), 2);
            assert.match(io.errText, /usage/);
        }
    });

    test("prints usage and exits 2 for a file that is not Markdown, before touching any file", async () => {
        const good = spec("design.md", DOC);
        const io = capture();
        assert.equal(await main([good, "diagram.mmd"], io), 2);
        assert.match(io.errText, /usage/);
        assert.equal(io.parses, 0);
        assert.equal(readFileSync(good, "utf8"), DOC);
    });

    test("renders the viewer and the links, then reports them current with --check", async () => {
        const path = spec("design.md", DOC);
        const io = capture();
        assert.equal(await main([path], io), 0);
        assert.equal(io.parses, 1);
        assert.match(io.outText, /design\.md: viewer written/);
        const viewerPath = viewerPlan(path, DOC).viewerPath;
        assert.equal(readFileSync(viewerPath, "utf8"), buildViewer(viewerPlan(path, DOC), "sha384-fake"));
        assert.equal(readFileSync(path, "utf8"), viewerPlan(path, DOC).doc);

        const check = capture();
        assert.equal(await main(["--check", path], check), 0);
        assert.equal(check.outText, `${path}: viewer OK\n`);
    });

    test("rendering twice leaves the files byte-identical and says they are up to date", async () => {
        const path = spec("design.md", DOC.replaceAll("\n", "\r\n"));
        await main([path], capture());
        const doc = readFileSync(path);
        const viewer = readFileSync(viewerPlan(path, DOC).viewerPath);
        const io = capture();
        assert.equal(await main([path], io), 0);
        assert.match(io.outText, /viewer up to date/);
        assert.deepEqual(readFileSync(path), doc);
        assert.deepEqual(readFileSync(viewerPlan(path, DOC).viewerPath), viewer);
    });

    test("--check reports a missing viewer and missing links, and writes nothing", async () => {
        const path = spec("design.md", DOC);
        const io = capture();
        assert.equal(await main(["--check", path], io), 1);
        assert.equal(io.outText, `${path}: viewer STALE missing viewer file; link lines missing or wrong\n`);
        assert.equal(readFileSync(path, "utf8"), DOC);
        assert.equal(existsSync(viewerPlan(path, DOC).viewerPath), false);
    });

    test("--check reports a viewer that differs", async () => {
        const path = spec("design.md", DOC);
        await main([path], capture());
        writeFileSync(viewerPlan(path, DOC).viewerPath, "edited");
        const io = capture();
        assert.equal(await main(["--check", path], io), 1);
        assert.equal(io.outText, `${path}: viewer STALE viewer differs\n`);
    });

    test("--check reports link lines that are wrong", async () => {
        const path = spec("design.md", DOC);
        await main([path], capture());
        writeFileSync(path, readFileSync(path, "utf8").replace("diagram-01-context-view", "diagram-01-old"));
        const io = capture();
        assert.equal(await main(["--check", path], io), 1);
        assert.equal(io.outText, `${path}: viewer STALE link lines missing or wrong\n`);
    });

    test("a parse failure in any file lists the failing blocks, writes nothing, and exits 1", async () => {
        const good = spec("good.md", DOC);
        const bad = spec("bad.md", "intro\n\n```mermaid\n" + BAD + "```\n");
        for (const argv of [[good, bad], ["--check", good, bad]]) {
            const io = capture();
            assert.equal(await main(argv, io), 1);
            assert.equal(io.outText, `${bad}: block 1 (line 3): FAIL Parse error on line 2\n`);
            assert.equal(io.hashes, 0);
        }
        assert.equal(readFileSync(good, "utf8"), DOC);
        assert.equal(existsSync(viewerPlan(good, DOC).viewerPath), false);
    });

    test("a document without diagrams is noted, left alone, and needs neither parser nor hash", async () => {
        const text = `# Plain\n\nstale ${VIEWER_MARKER}\n`;
        const path = spec("plain.md", text);
        for (const argv of [[path], ["--check", path]]) {
            const io = capture();
            assert.equal(await main(argv, io), 0);
            assert.equal(io.outText, `${path}: no Mermaid diagrams\n`);
            assert.equal(io.parses + io.hashes, 0);
        }
        assert.equal(readFileSync(path, "utf8"), text);
    });

    test("hashes Mermaid once for several documents", async () => {
        const io = capture();
        assert.equal(await main([spec("a.md", DOC), spec("b.md", DOC)], io), 0);
        assert.equal(io.hashes, 1);
    });
});

describe("the script", () => {
    test("runs as a CLI and exits 2 on a usage error", () => {
        const result = spawnSync(process.execPath, [SCRIPT, "--check", "diagram.mmd"], { encoding: "utf8" });
        assert.equal(result.status, 2, result.stderr);
        assert.match(result.stderr, /usage: render_diagrams\.mjs/);
    });

    test("renders with the real parser and hash, then passes --check", () => {
        const path = spec("real.md", DOC);
        const render = spawnSync(process.execPath, [SCRIPT, path], { encoding: "utf8" });
        assert.equal(render.status, 0, render.stderr);
        assert.match(readFileSync(viewerPlan(path, DOC).viewerPath, "utf8"), /integrity="sha384-[A-Za-z0-9+/]{64}"/);
        const check = spawnSync(process.execPath, [SCRIPT, "--check", path], { encoding: "utf8" });
        assert.equal(check.status, 0, check.stderr);
        assert.equal(check.stdout, `${path}: viewer OK\n`);
    });
});
