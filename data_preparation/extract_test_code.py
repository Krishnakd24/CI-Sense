"""Retry only FILE_OR_METHOD_NOT_FOUND rows; Python 3.10+, standard library only.

Uses V1's repository-tree -> raw-source -> brace-matching approach, with XML
identity resolution, parameterized names, package-aware paths and inheritance.
Original successful rows and all metadata are preserved. See the audit CSV for
unresolved/ambiguous cases. No test identity is guessed from an unrelated failure.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.request
import xml.etree.ElementTree as ET

MISSING = 'FILE_OR_METHOD_NOT_FOUND'
BASE = Path(__file__).resolve().parent


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, columns):
    with Path(path).open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def method_name(name):
    # Keep the complete runtime name in test_name; normalize only source lookup.
    return re.sub(r'\[.*\]$', '', name)


def resolve_xml(root, project, original):
    path = root / project / (original + '.xml')
    if not path.is_file():
        return original, 'XML_NOT_FOUND', []
    try:
        tree = ET.parse(path)
    except (ET.ParseError, OSError) as exc:
        return None, 'XML_ERROR: ' + str(exc), []
    cases = []
    for case in tree.iter():
        if case.tag.rsplit('}', 1)[-1] != 'testcase':
            continue
        if not any(c.tag.rsplit('}', 1)[-1] in ('failure', 'error') for c in case):
            continue
        if case.get('classname') and case.get('name'):
            identifier = case.get('classname') + '#' + case.get('name')
            if identifier not in cases:
                cases.append(identifier)
    if original in cases:
        return original, 'XML_EXACT', cases
    original_class, _, original_method = original.partition('#')
    same_method = [x for x in cases if method_name(x.split('#', 1)[1]) == method_name(original_method)]
    same_class_method = [x for x in same_method if x.split('#', 1)[0] == original_class]
    candidates = same_class_method or same_method
    if len(candidates) == 1:
        return candidates[0], 'XML_CORRECTED', cases
    if len(cases) == 1:
        return cases[0], 'XML_SINGLE_FAILURE', cases
    return None, 'XML_AMBIGUOUS' if cases else 'XML_NO_FAILURE', cases


def mask_java(source):
    # Preserve offsets/newlines while hiding comments and string/char literals.
    pattern = r'"""[\s\S]*?"""|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*[\s\S]*?\*/'
    return re.sub(pattern, lambda m: ''.join('\n' if c == '\n' else ' ' for c in m[0]), source)


def extract_method_code(source, name):
    """Match declarations, not method calls; ignore braces inside strings/comments."""
    masked = mask_java(source)
    pattern = r'(?m)^[ \t]*(?:@[\w.]+\s+)*(?:(?:public|protected|private|static|final|synchronized|abstract|native|default)\s+)*(?:<[^;{}]+>\s+)?[\w.$<>\[\],?]+\s+' + re.escape(name) + r'\s*\([^;{}]*\)\s*(?:throws\s+[\w.,\s]+)?\{'
    matches = list(re.finditer(pattern, masked))
    if len(matches) != 1:
        return None
    match = matches[0]
    start = match.start()
    # Include immediately preceding, single-line annotations.
    while start > 0:
        previous = masked.rfind('\n', 0, max(0, start - 1)) + 1
        if not masked[previous:start].strip().startswith('@'):
            break
        start = previous
    depth = 1
    for end in range(match.end(), len(masked)):
        depth += (masked[end] == '{') - (masked[end] == '}')
        if depth == 0:
            return source[start:end + 1].strip()
    return None


class Sources:
    def __init__(self, project, info, args):
        self.project, self.args = project, args
        self.sha = info['SHA'].strip()
        self.repo = info['URL'].strip().rstrip('/').removesuffix('.git').split('github.com/')[-1]
        self.local = args.sources_root / project if args.sources_root else None
        self.cache = args.cache / project / self.sha
        self.cache.mkdir(parents=True, exist_ok=True)
        self.contents = {}
        if self.local:
            # Read the configured commit, never an arbitrary working-tree revision.
            result = self.git('ls-tree', '-r', '--name-only', self.sha)
            self.paths = result.splitlines()
        else:
            tree = json.loads(self.download(f'https://api.github.com/repos/{self.repo}/git/trees/{self.sha}?recursive=1'))
            if tree.get('truncated'):
                raise ValueError('GitHub repository tree is truncated; use --sources-root')
            self.paths = [x['path'] for x in tree['tree'] if x['type'] == 'blob']

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.local), *args], check=True, capture_output=True, encoding='utf-8').stdout

    def download(self, url):
        path = self.cache / (hashlib.sha256(url.encode()).hexdigest() + '.txt')
        if path.is_file():
            return path.read_text(encoding='utf-8')
        if self.args.offline:
            raise OSError('Source not cached (offline mode)')
        headers = {'User-Agent': 'failed-test-extractor-v2'}
        if os.environ.get('GITHUB_TOKEN'):
            headers['Authorization'] = 'Bearer ' + os.environ['GITHUB_TOKEN']
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
            data = response.read().decode('utf-8')
        path.write_text(data, encoding='utf-8')
        return data

    def content(self, path):
        if path not in self.contents:
            self.contents[path] = self.git('show', f'{self.sha}:{path}') if self.local else self.download(f'https://raw.githubusercontent.com/{self.repo}/{self.sha}/{path}')
        return self.contents[path]

    def find_method(self, classname, name, seen=None):
        seen = set() if seen is None else seen
        if classname in seen:
            return None
        seen.add(classname)
        outer = classname.split('$')[0]
        suffix = outer.replace('.', '/') + '.java'
        paths = [p for p in self.paths if p == suffix or p.endswith('/' + suffix)]
        if not paths:
            paths = [p for p in self.paths if p.rsplit('/', 1)[-1] == outer.split('.')[-1] + '.java']
        results = []
        for path in paths:
            source = self.content(path)
            masked = mask_java(source)
            package = re.search(r'\bpackage\s+([\w.]+)\s*;', masked)
            if (package[1] if package else '') != outer.rpartition('.')[0]:
                continue
            code = extract_method_code(source, name)
            if code:
                results.append((code, path, classname + '#' + name))
                continue
            parent = re.search(r'\bclass\s+' + re.escape(classname.split('$')[-1].split('.')[-1]) + r'(?:\s*<[^{}]+?>)?\s+extends\s+([\w.$]+)', masked)
            if parent:
                parent_name = parent[1]
                if '.' not in parent_name:
                    imported = re.search(r'\bimport\s+([\w.]+\.' + re.escape(parent_name) + r')\s*;', masked)
                    parent_name = imported[1] if imported else outer.rpartition('.')[0] + '.' + parent_name
                inherited = self.find_method(parent_name, name, seen.copy())
                if inherited:
                    results.append(inherited)
        return results[0] if len(results) == 1 else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=BASE / 'extracted_test_code_V1.csv')
    parser.add_argument('--output', type=Path, default=BASE / 'extracted_test_code_retry.csv')
    parser.add_argument('--audit', type=Path, default=BASE / 'extracted_test_code_retry_audit.csv')
    parser.add_argument('--comparison', type=Path, default=BASE / 'xml_test_name_comparison.csv')
    parser.add_argument('--project-info', type=Path, default=BASE / 'Project_Info.csv')
    parser.add_argument('--xml-root', type=Path, default=BASE)
    parser.add_argument('--sources-root', type=Path, help='Folder containing project-named Git checkouts with configured SHAs')
    parser.add_argument('--cache', type=Path, default=BASE / '.test_code_v2_cache')
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error('Output must differ from input')
    rows = read_csv(args.input)
    comparisons = {}
    for item in read_csv(args.comparison):
        if item['same'].lower() == 'false' and item['corrected_test_name']:
            comparisons.setdefault(item['xml_file_name'], set()).add(item['corrected_test_name'])
    info = {r['Project'].strip(): r for row in read_csv(args.project_info) for r in [{k.strip(): v for k, v in row.items() if k}]}
    sources, audit = {}, []
    for index, row in enumerate(rows):
        if row['Test_code'] not in (MISSING, 'NA', ''):
            continue
        project, original = row['Project_name'], row['test_name']
        candidates = comparisons.get(original + '.xml', set())
        resolved, xml_status, cases = original, 'ORIGINAL', sorted(candidates)
        record = dict(row_number=index + 2, Project_name=project, original_test_name=original,
                      resolved_test_name=resolved or '', xml_status=xml_status,
                      xml_failed_tests=json.dumps(cases), status='', source_file='', source_identifier='', detail='')
        if resolved:
            classname, separator, runtime_name = resolved.partition('#')
            name = method_name(runtime_name)
            if not separator or not re.fullmatch(r'[A-Za-z_$][\w$]*', name) or name in ('initializationError', 'classMethod'):
                record['status'] = 'NO_TEST_METHOD'
            else:
                try:
                    if project not in sources:
                        try:
                            sources[project] = Sources(project, info[project], args)
                        except Exception as exc:
                            sources[project] = exc
                    if isinstance(sources[project], Exception):
                        raise sources[project]
                    result = sources[project].find_method(classname, name)
                    if not result and len(candidates) == 1:
                        corrected = next(iter(candidates))
                        # Verify the comparison against this project's XML; the CSV
                        # contains filenames but no project column.
                        xml_id, _, _ = resolve_xml(args.xml_root, project, original)
                        if xml_id == corrected:
                            corrected_class, sep, corrected_method = corrected.partition('#')
                            if sep:
                                result = sources[project].find_method(corrected_class, method_name(corrected_method))
                                if result:
                                    record['resolved_test_name'] = corrected
                                    record['xml_status'] = 'COMPARISON_CORRECTED'
                    if result:
                        row['Test_code'], record['source_file'], record['source_identifier'] = result
                        record['status'] = 'RECOVERED'
                    else:
                        record['status'] = 'SOURCE_METHOD_NOT_FOUND_OR_AMBIGUOUS'
                except Exception as exc:
                    record['status'], record['detail'] = 'SOURCE_UNAVAILABLE', str(exc)
        else:
            record['status'] = xml_status
        audit.append(record)
        print(f"{project}: {original} -> {record['status']}", flush=True)
    write_csv(args.output, rows, list(rows[0]))
    if audit:
        write_csv(args.audit, audit, list(audit[0]))
    recovered = sum(r['status'] == 'RECOVERED' for r in audit)
    print(f'Retried {len(audit)}; recovered {recovered}; unresolved {len(audit)-recovered}; preserved {len(rows)-len(audit)} successful rows.')


if __name__ == '__main__':
    main()
