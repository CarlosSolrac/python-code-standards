#!/usr/bin/env node
// Parse every Mermaid diagram in a file with Mermaid's own parser: syntax only, no rendering.
// Markdown files are checked block by block (```mermaid fences); .mmd and .mermaid files are one diagram each.
//
//   node validate_mermaid.mjs <file>...   prints one line per diagram; exits 1 if any fails, 2 on usage error
//   node validate_mermaid.mjs --hook      Claude Code PostToolUse hook: reads the hook's JSON on stdin and, when
//                                         the edited file has a failing diagram, lists it on stderr and exits 2
//
// Mermaid and jsdom are installed at the exact versions in PINS into a shared cache folder on first use
// (DESIGN_SPEC_MERMAID_CACHE, default ~/.cache/design-spec-mermaid), so no project gains npm files.
// Needs Node 22.22.2+ or 24.15+, the pinned jsdom's minimum. Versions without import.meta.main exit 2 with that
// message; other unsupported versions fail when jsdom loads (exit 2 in hook mode, an uncaught error from the CLI).
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { extname, join } from "node:path";
import { pathToFileURL } from "node:url";

export const PINS = Object.freeze({ mermaid: "11.17.2", jsdom: "30.1.1" });

// Lives in the cache folder, so its imports resolve against the cache's node_modules. Mermaid is imported
// lazily because it expects a DOM, which must exist before the module is evaluated.
const LOADER = 'export { JSDOM } from "jsdom";\nexport const importMermaid = () => import("mermaid");\n';
const USAGE = "usage: validate_mermaid.mjs <file>... | --hook (reads the hook's JSON on stdin)\n";

/** Return the diagrams in a file as { line, source }, where line is where the diagram starts. */
export function extractDiagrams(path, text) {
    const extension = extname(path).toLowerCase();
    if (extension === ".mmd" || extension === ".mermaid") {
        return [{ line: 1, source: text }];
    }
    if (extension !== ".md") {
        return [];
    }
    const diagrams = [];
    for (const match of text.matchAll(/```mermaid[ \t]*\r?\n([\s\S]*?)```/g)) {
        diagrams.push({ line: text.slice(0, match.index).split("\n").length, source: match[1] });
    }
    return diagrams;
}

/** Return the folder that holds the pinned packages. */
export function cacheDir(env, home) {
    return env.DESIGN_SPEC_MERMAID_CACHE ?? join(home, ".cache", "design-spec-mermaid");
}

function installedVersion(dir, name) {
    const manifest = join(dir, "node_modules", name, "package.json");
    return existsSync(manifest) ? JSON.parse(readFileSync(manifest, "utf8")).version : undefined;
}

/** Run npm install for the given package specs inside dir. The specs are fixed pins, never user input. */
export function npmInstall(dir, specs) {
    return spawnSync(`npm install --no-audit --no-fund --loglevel=error --save-exact ${specs.join(" ")}`, { cwd: dir, shell: true, encoding: "utf8" });
}

/** Make sure dir holds exactly the pinned packages and the loader, installing them if not; return dir. */
export function ensureDeps(dir, install = npmInstall) {
    const pinned = Object.entries(PINS);
    if (pinned.every(([name, version]) => installedVersion(dir, name) === version) && existsSync(join(dir, "loader.mjs"))) {
        return dir;
    }
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, "package.json"), '{ "private": true }\n');
    const result = install(dir, pinned.map(([name, version]) => `${name}@${version}`));
    if (result.status !== 0) {
        throw new Error(`npm install failed in ${dir}: ${result.stderr}`);
    }
    writeFileSync(join(dir, "loader.mjs"), LOADER);
    return dir;
}

/** Load Mermaid from dir and return parse(source) -> { ok, detail }, where detail is the type or the error. */
export async function loadParser(dir) {
    const { JSDOM, importMermaid } = await import(pathToFileURL(join(dir, "loader.mjs")).href);
    const dom = new JSDOM("<!doctype html><html><body></body></html>");
    globalThis.window = dom.window;
    globalThis.document = dom.window.document;
    globalThis.DOMParser = dom.window.DOMParser;
    const { default: mermaid } = await importMermaid();
    mermaid.initialize({ startOnLoad: false });
    return async (source) => {
        try {
            return { ok: true, detail: (await mermaid.parse(source)).diagramType };
        } catch (error) {
            return { ok: false, detail: String(error).split("\n").slice(0, 4).join(" | ") };
        }
    };
}

/** Parse every diagram in the file at path; getParse is called only when the file has diagrams. */
export async function checkFile(path, getParse) {
    const diagrams = extractDiagrams(path, readFileSync(path, "utf8"));
    if (diagrams.length === 0) {
        return [];
    }
    const parse = await getParse();
    const results = [];
    for (const [index, diagram] of diagrams.entries()) {
        results.push({ block: index + 1, line: diagram.line, ...(await parse(diagram.source)) });
    }
    return results;
}

/** Run the CLI or hook; io supplies stdin(), out(text), err(text), and getParse(). Return the exit code. */
export async function main(argv, io) {
    let parser;
    const getParse = async () => (parser ??= await io.getParse());
    if (argv[0] === "--hook") {
        const path = JSON.parse(io.stdin()).tool_input.file_path;
        let failures;
        try {
            failures = (await checkFile(path, getParse)).filter((result) => !result.ok);
        } catch (error) {
            io.err(`Mermaid check could not run: ${error.message}\n`);
            return 2;
        }
        if (failures.length === 0) {
            return 0;
        }
        for (const failure of failures) {
            io.err(`${path}: block ${failure.block} (line ${failure.line}): FAIL ${failure.detail}\n`);
        }
        io.err("Fix the failing Mermaid diagram(s) before showing them to the user.\n");
        return 2;
    }
    if (argv.length === 0) {
        io.err(USAGE);
        return 2;
    }
    let failed = 0;
    for (const path of argv) {
        const results = await checkFile(path, getParse);
        if (results.length === 0) {
            io.out(`${path}: no Mermaid diagrams\n`);
        }
        for (const result of results) {
            io.out(`${path}: block ${result.block} (line ${result.line}): ${result.ok ? "OK" : "FAIL"} ${result.detail}\n`);
            failed += result.ok ? 0 : 1;
        }
    }
    return failed === 0 ? 0 : 1;
}

/**
 * Run when isMain (import.meta.main) is true and return the exit code; return undefined when imported. Node
 * versions without import.meta.main would otherwise skip every check and exit 0, so they fail with code 2.
 */
export async function start(isMain, run, io) {
    if (isMain === undefined) {
        io.err(`validate_mermaid.mjs needs Node 22.22.2+ or 24.15+ (the pinned jsdom's minimum); found ${process.version}\n`);
        return 2;
    }
    return isMain ? run() : undefined;
}

const processIo = {
    stdin: () => readFileSync(0, "utf8"),
    out: (text) => process.stdout.write(text),
    err: (text) => process.stderr.write(text),
    getParse: () => loadParser(ensureDeps(cacheDir(process.env, homedir()))),
};
const exitCode = await start(import.meta.main, () => main(process.argv.slice(2), processIo), processIo);
if (exitCode !== undefined) {
    process.exitCode = exitCode;
}
