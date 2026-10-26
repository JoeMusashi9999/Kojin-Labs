#!/usr/bin/env python3
"""Validate the Git-backed archive and produce a static, searchable manifest."""
import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import quote, urlparse

ALLOWED = {'.pdf', '.xlsx', '.xls', '.ods', '.csv', '.tsv', '.pptx', '.ppt', '.odp',
           '.docx', '.doc', '.odt', '.txt', '.md', '.png', '.jpg', '.jpeg', '.gif',
           '.webp', '.svg', '.zip', '.json'}
RECORD_FIELDS = {'id', 'title', 'created', 'description', 'researchers', 'tags',
                 'preview', 'supersedes', 'source_url'}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read_json(path):
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f'{path}: duplicate JSON key {key}')
            result[key] = value
        return result
    value = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique_keys)
    require(isinstance(value, dict), f'{path}: expected a JSON object')
    return value


def string(value, label, maximum=2000):
    require(isinstance(value, str) and 0 < len(value.strip()) <= maximum,
            f'{label}: expected nonempty text, at most {maximum} characters')
    return value.strip()


def string_list(value, label):
    require(isinstance(value, list), f'{label}: expected a list')
    require(len(value) <= 50, f'{label}: too many values')
    values = [string(v, label, 120) for v in value]
    require(len(values) == len(set(values)), f'{label}: duplicate values')
    return values


def contained_file(path, root):
    require(path.is_file() and not path.is_symlink(), f'{path}: missing file or symlink')
    require(path.resolve().is_relative_to(root.resolve()), f'{path}: outside content folder')
    require(path.stat().st_size < 100 * 1024 * 1024, f'{path}: must be smaller than 100 MiB')
    return path


def descriptor(path, root):
    contained_file(path, root)
    extension = path.suffix.lower()
    require(extension in ALLOWED, f'{path}: unsupported extension {extension}')
    relative = path.relative_to(root).as_posix()
    return {'path': 'archive-content/' + relative,
            'name': path.name, 'extension': extension[1:],
            'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def build_manifest(root, repository='', revision=''):
    require(root.is_dir(), 'Missing archive-content folder')
    require(not root.is_symlink(), 'Content root cannot be a symlink')
    sections, records, consumed = [], [], set()
    for path in root.rglob('*'):
        require(not path.is_symlink(), f'{path}: symlinks are not allowed')
    for config in sorted(root.rglob('_section.json')):
        require(config.parent != root, 'Sections must be subfolders of archive-content')
        data = read_json(config)
        require(set(data) <= {'title', 'description', 'order'}, f'{config}: unknown field')
        key = config.parent.relative_to(root).as_posix()
        require(all(not p.startswith('.') for p in Path(key).parts), f'{config}: hidden folder')
        order = data.get('order', 100)
        require(type(order) is int, f'{config}: order must be an integer')
        sections.append({'id': key, 'title': string(data.get('title'), str(config), 120),
                         'description': string(data.get('description'), str(config)), 'order': order})
        consumed.add(config)
    section_ids = {s['id'] for s in sections}
    for sidecar in sorted(root.rglob('*.meta.json')):
        data = read_json(sidecar)
        require(set(data) <= RECORD_FIELDS, f'{sidecar}: unknown metadata field')
        section = sidecar.parent.relative_to(root).as_posix()
        require(section in section_ids, f'{sidecar}: add _section.json in this folder')
        file_path = sidecar.with_name(sidecar.name[:-len('.meta.json')])
        asset = descriptor(file_path, root)
        record_id = string(data.get('id'), str(sidecar), 100)
        require(re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', record_id), f'{sidecar}: invalid id')
        created = data.get('created')
        require(isinstance(created, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', created),
                f'{sidecar}: created must be YYYY-MM-DD')
        dt.date.fromisoformat(created)
        record = {'id': record_id, 'section': section,
                  'title': string(data.get('title'), str(sidecar), 200),
                  'created': created, 'description': string(data.get('description'), str(sidecar)),
                  'researchers': string_list(data.get('researchers'), str(sidecar)),
                  'tags': string_list(data.get('tags', []), str(sidecar)), 'file': asset}
        if data.get('supersedes'):
            record['supersedes'] = string(data['supersedes'], str(sidecar), 100)
        if data.get('source_url'):
            url = urlparse(string(data['source_url'], str(sidecar)))
            require(url.scheme == 'https' and url.netloc and not url.username and not url.password,
                    f'{sidecar}: source_url must be an HTTPS link')
            record['source_url'] = data['source_url']
        if data.get('preview'):
            preview_name = string(data['preview'], str(sidecar), 255)
            require(Path(preview_name).name == preview_name and '/' not in preview_name and '\\' not in preview_name,
                    f'{sidecar}: preview must be a filename in the same folder')
            preview = file_path.parent / preview_name
            require(preview.suffix.lower() == '.pdf', f'{sidecar}: preview must be a PDF')
            require(preview != file_path, f'{sidecar}: preview must differ from the original')
            record['preview'] = descriptor(preview, root)
            consumed.add(preview)
        if repository and revision:
            record['source_commit'] = f'https://github.com/{repository}/blob/{revision}/' + quote(asset['path'], safe='/')
        records.append(record)
        consumed.update([sidecar, file_path])
    ids = [r['id'] for r in records]
    require(len(ids) == len(set(ids)), 'Every record must have a unique id')
    by_id = {r['id']: r for r in records}
    for record in records:
        seen = {record['id']}
        ancestor = record.get('supersedes')
        while ancestor:
            require(ancestor in by_id, f"{record['id']}: supersedes target does not exist")
            require(ancestor not in seen, f"{record['id']}: cyclic revision history")
            seen.add(ancestor)
            ancestor = by_id[ancestor].get('supersedes')
    files = {p for p in root.rglob('*') if p.is_file()}
    unlisted = files - consumed
    require(not unlisted, 'Files without metadata or a preview reference: ' + ', '.join(str(p) for p in sorted(unlisted)))
    require(len(records) <= 10000, 'Archive exceeds the static catalog limit')
    sections.sort(key=lambda s: (s['order'], s['title'].lower()))
    records.sort(key=lambda r: (r['created'], r['id']), reverse=True)
    return {'schema_version': 1, 'revision': revision or None, 'sections': sections, 'records': records}


def check_append_only(repository_root, base):
    """A published file is never edited, renamed, or deleted. New names are fine."""
    require(re.fullmatch(r'[0-9a-fA-F]{40}', base or ''), 'Base revision must be a full Git SHA')
    def tree(revision):
        output = subprocess.check_output(['git', 'ls-tree', '-r', '-z', revision,
                                          '--', 'archive-content/'], cwd=repository_root)
        result = {}
        for entry in output.split(b'\0'):
            if entry:
                metadata, path = entry.split(b'\t', 1)
                result[path.decode('utf-8')] = metadata.split()[2].decode('ascii')
        return result
    # First-parent history follows published main snapshots, not intermediate PR
    # edits. Remember the first published blob for every path, even if a failed
    # push later edited or deleted it. A later unrelated push cannot bypass this.
    commits = subprocess.check_output(['git', 'log', '--first-parent', '--reverse',
                                      '--format=%H', base, '--', 'archive-content/'],
                                     cwd=repository_root).decode().splitlines()
    frozen = {}
    for commit in commits:
        for path, blob in tree(commit).items():
            frozen.setdefault(path, blob)
    current = tree('HEAD')
    violations = [path for path, blob in frozen.items() if current.get(path) != blob]
    require(not violations, 'Archive is append-only. Add a new version instead:\n' + '\n'.join(violations))



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path)
    parser.add_argument('--base', default='')
    parser.add_argument('--repository', default='JoeMusashi9999/Kojin-Labs')
    parser.add_argument('--revision', default='')
    args = parser.parse_args()
    root = args.root.resolve()
    require(re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', args.repository), 'Invalid repository')
    require(not args.revision or re.fullmatch(r'[0-9a-fA-F]{40}', args.revision), 'Invalid revision')
    if args.base and set(args.base) != {'0'}:
        check_append_only(root, args.base)
    manifest = build_manifest(root / 'archive-content', args.repository, args.revision)
    output = args.output or root / 'archive' / 'manifest.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f"Archive validated: {len(manifest['records'])} records, {len(manifest['sections'])} sections")


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(f'Archive validation failed: {error}')
