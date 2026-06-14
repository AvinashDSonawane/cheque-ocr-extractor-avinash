"""
utils/dbf_handler.py
--------------------
Handles all DBF-related operations for the Cheque OCR Extractor.

Write strategy
--------------
Rather than relying on the dbf library's VfpTable write API (which has
proved unreliable across versions), we write changes DIRECTLY into the
DBF binary file at the exact byte offsets of each field.  This is safe,
fast, and works regardless of the DBF sub-version (dBASE III/IV/VFP).

Fields updated per matched record
----------------------------------
  DRAWER_NM  (C, 50)  — extracted drawer name, space-padded
  FILE_MARK  (L,  1)  — b'F' when drawer name present, b'T' when blank
  OPR_NO     (C,  5)  — always b'AS601'
"""

import os
import re
import ntpath
import struct
import shutil
from typing import List, Dict, Optional, Tuple

# ---------------------------------------------------------------------------
# ── CONFIGURABLE CONSTANTS ────────────────────────────────────────────────
FILENAME_FIELD   = 'FILE_NAME'   # DBF column used for filename matching
IMAGE_FILE_FIELD = 'IMAGE_FILE'  # Bare-filename fallback column
DRAWER_FIELD     = 'DRAWER_NM'
FILE_MARK_FIELD  = 'FILE_MARK'
OPR_NO_FIELD     = 'OPR_NO'
OPR_NO_VALUE     = 'AS601'
DRAWER_FIELD_WIDTH = 50          # overridden at runtime from actual schema in write_dbf

# ---------------------------------------------------------------------------
# ── HELPERS ───────────────────────────────────────────────────────────────

def _strip(value) -> str:
    if value is None:
        return ''
    return str(value).strip()


def _normalise_filename(name: str) -> str:
    """
    Normalise a filename for case/extension/path-insensitive matching.
    Handles Windows backslash paths stored in DBF fields.
    """
    name = name.strip()
    # Strip Windows or Unix path components
    name = ntpath.basename(name)   # handles backslashes
    name = os.path.basename(name)  # handles forward slashes
    name = name.lower()
    # Strip any file extension (any suffix up to 5 chars)
    name = re.sub(r'\.[a-z0-9]{1,5}$', '', name)
    return name


# ---------------------------------------------------------------------------
# ── LOW-LEVEL DBF PARSER (read-only, no external library) ─────────────────

def _parse_dbf_header(data: bytes):
    """
    Parse a DBF file's binary header.
    Returns (num_records, header_size, record_size, fields)
    where fields = list of (name, type, offset_in_record, length)

    Supports dBASE III/IV and Visual FoxPro (VFP).

    VFP field descriptors store the actual in-record byte displacement at
    bytes 12-15 of each 32-byte field descriptor (little-endian uint32).
    dBASE III leaves those bytes as zero.  We prefer the stored displacement
    when it is present and plausible; otherwise we accumulate from the
    deletion-flag byte (offset 1), which is the correct dBASE III behaviour.
    """
    num_records = struct.unpack_from('<I', data, 4)[0]
    header_size = struct.unpack_from('<H', data, 8)[0]
    record_size = struct.unpack_from('<H', data, 10)[0]

    fields     = []
    rec_offset = 1   # first byte of every record is the deletion flag
    offset     = 32  # field descriptors start at byte 32

    while offset + 32 <= header_size:
        fd = data[offset:offset + 32]
        if fd[0] in (0x0D, 0x00):   # header terminator or null padding
            break

        name   = fd[0:11].replace(b'\x00', b'').decode('ascii', 'replace').strip()
        ftype  = chr(fd[11])
        length = fd[16]

        # FIX (Bug 1): VFP stores the actual in-record displacement at bytes 12-15.
        # Prefer it when nonzero and within the record bounds; otherwise accumulate.
        stored_disp = struct.unpack_from('<I', fd, 12)[0]
        if stored_disp and stored_disp < record_size:
            actual_offset = stored_disp          # VFP: use stored displacement
        else:
            actual_offset = rec_offset           # dBASE III/IV: use accumulated value

        fields.append((name, ftype, actual_offset, length))
        rec_offset = actual_offset + length      # advance accumulator past this field
        offset    += 32

    return num_records, header_size, record_size, fields


def _read_record(data: bytes, header_size: int, record_size: int,
                 fields: list, index: int) -> Dict:
    """Read one record (by index) into a dict of stripped strings."""
    start = header_size + index * record_size
    raw   = data[start:start + record_size]
    row   = {}
    for name, ftype, off, length in fields:
        raw_val = raw[off:off + length]
        if ftype == 'L':
            # Logical: 'T'/'t'/'Y'/'y' = True, else False
            row[name] = raw_val.decode('latin-1', 'replace').strip()
        else:
            row[name] = raw_val.decode('latin-1', 'replace').strip()
    return row


# ---------------------------------------------------------------------------
# ── PUBLIC READ API ────────────────────────────────────────────────────────

def read_dbf(dbf_path: str) -> Tuple[List[Dict], List[str]]:
    """Read a DBF and return (records, field_names)."""
    if not os.path.isfile(dbf_path):
        raise FileNotFoundError(f'DBF file not found: {dbf_path}')

    with open(dbf_path, 'rb') as f:
        data = f.read()

    num_records, header_size, record_size, fields = _parse_dbf_header(data)
    field_names = [f[0] for f in fields]

    # Validate required fields exist
    match_field = IMAGE_FILE_FIELD if IMAGE_FILE_FIELD in field_names else FILENAME_FIELD
    for required in (match_field, DRAWER_FIELD, FILE_MARK_FIELD, OPR_NO_FIELD):
        if required not in field_names:
            raise ValueError(
                f"Required field '{required}' not found in DBF.\n"
                f"Available fields: {field_names}"
            )

    records = []
    for i in range(num_records):
        records.append(_read_record(data, header_size, record_size, fields, i))

    return records, field_names


def load_dbf_for_display(dbf_path: str) -> Tuple[List[Dict], List[str], str]:
    records, field_names = read_dbf(dbf_path)
    summary = (
        f"DBF loaded: {os.path.basename(dbf_path)}  |  "
        f"{len(records)} record(s)  |  "
        f"Fields: {', '.join(field_names)}"
    )
    return records, field_names, summary


# ---------------------------------------------------------------------------
# ── MERGE ─────────────────────────────────────────────────────────────────

def merge_ocr_into_dbf_records(
    dbf_records:  List[Dict],
    ocr_results:  List[Dict],
) -> Tuple[List[Dict], int, int]:
    """Match OCR results to DBF records by filename and merge drawer names."""

    # Build OCR lookup: normalised_filename → drawer_name
    ocr_lookup: Dict[str, str] = {}
    for res in ocr_results:
        fname  = _normalise_filename(res.get('file_name', ''))
        drawer = res.get('drawer_name', '').strip()
        if fname:
            ocr_lookup[fname] = drawer

    matched   = 0
    unmatched = len(ocr_lookup)

    updated_records = []
    for rec in dbf_records:
        rec_copy = dict(rec)
        rec_copy[OPR_NO_FIELD] = OPR_NO_VALUE

        # Try IMAGE_FILE first (bare filename), fall back to FILE_NAME
        raw_fname = rec_copy.get(IMAGE_FILE_FIELD) or rec_copy.get(FILENAME_FIELD, '')
        norm      = _normalise_filename(raw_fname)

        if norm in ocr_lookup:
            drawer = ocr_lookup[norm][:DRAWER_FIELD_WIDTH]
            rec_copy[DRAWER_FIELD]    = drawer
            rec_copy[FILE_MARK_FIELD] = 'F' if drawer else 'T'
            matched   += 1
            unmatched -= 1

        updated_records.append(rec_copy)

    return updated_records, matched, unmatched


# ---------------------------------------------------------------------------
# ── DIRECT BINARY WRITE ────────────────────────────────────────────────────

def write_dbf(dbf_path: str, updated_records: List[Dict],
              field_names: List[str], output_path: str = None) -> str:
    """
    Write updated records directly into the DBF binary file.

    Only DRAWER_NM, FILE_MARK, and OPR_NO are modified.
    Every other byte in the file is left completely untouched.
    """
    target = output_path if output_path else dbf_path

    # Copy to target first if saving-as
    if target != dbf_path:
        shutil.copy2(dbf_path, target)
        base_src = os.path.splitext(dbf_path)[0]
        base_dst = os.path.splitext(target)[0]
        for ext in ('.dbt', '.cdx', '.fpt', '.mdx'):
            if os.path.isfile(base_src + ext):
                shutil.copy2(base_src + ext, base_dst + ext)

    with open(target, 'rb') as f:
        data = bytearray(f.read())

    num_records, header_size, record_size, fields = _parse_dbf_header(bytes(data))

    # Build field-offset map from parsed header
    field_map = {name: (off, length, ftype) for name, ftype, off, length in fields}

    # Validate all three target fields exist
    for fname in (DRAWER_FIELD, FILE_MARK_FIELD, OPR_NO_FIELD):
        if fname not in field_map:
            raise ValueError(f"Field '{fname}' not found in DBF. Available: {list(field_map)}")

    drawer_off,    drawer_len,    _ = field_map[DRAWER_FIELD]
    file_mark_off, file_mark_len, _ = field_map[FILE_MARK_FIELD]
    opr_no_off,    opr_no_len,    _ = field_map[OPR_NO_FIELD]

    changes = 0
    for i, rec_data in enumerate(updated_records):
        if i >= num_records:
            break

        rec_start = header_size + i * record_size

        # ── DRAWER_NM ─────────────────────────────────────────────────
        drawer_val   = rec_data.get(DRAWER_FIELD, '')[:drawer_len]
        drawer_bytes = drawer_val.encode('latin-1', 'replace').ljust(drawer_len, b' ')
        data[rec_start + drawer_off : rec_start + drawer_off + drawer_len] = drawer_bytes

        # ── FILE_MARK (Logical: b'F'=found/True, b'T'=todo/False) ─────
        file_mark_val = rec_data.get(FILE_MARK_FIELD, 'T')
        if isinstance(file_mark_val, bool):
            mark_char = b'F' if file_mark_val else b'T'
        else:
            mark_char = b'F' if str(file_mark_val).upper() == 'F' else b'T'
        # FIX (Bug 2): pad mark_char to exactly file_mark_len bytes so the
        # bytearray slice assignment never resizes the array and corrupts the file.
        mark_bytes = mark_char.ljust(file_mark_len, b' ')
        data[rec_start + file_mark_off : rec_start + file_mark_off + file_mark_len] = mark_bytes

        # ── OPR_NO ────────────────────────────────────────────────────
        opr_val   = rec_data.get(OPR_NO_FIELD, OPR_NO_VALUE)[:opr_no_len]
        opr_bytes = opr_val.encode('latin-1', 'replace').ljust(opr_no_len, b' ')
        data[rec_start + opr_no_off : rec_start + opr_no_off + opr_no_len] = opr_bytes

        changes += 1

    with open(target, 'wb') as f:
        f.write(data)

    return target


# ---------------------------------------------------------------------------
# ── ONE-SHOT HELPER ────────────────────────────────────────────────────────

def apply_and_save(dbf_path: str, ocr_results: List[Dict],
                   output_path: Optional[str] = None) -> Dict:
    records, field_names, _ = load_dbf_for_display(dbf_path)
    updated, matched, unmatched = merge_ocr_into_dbf_records(records, ocr_results)
    written = write_dbf(dbf_path, updated, field_names, output_path)
    return {
        'output_path':    written,
        'matched':        matched,
        'unmatched':      unmatched,
        'total_dbf_rows': len(records),
    }


# ---------------------------------------------------------------------------
# ── DIAGNOSTIC HELPER ─────────────────────────────────────────────────────

def diagnose_match(dbf_records: List[Dict], ocr_results: List[Dict]) -> List[str]:
    lines = ['── DBF filename samples (raw → normalised) ──']
    for rec in dbf_records[:8]:
        raw  = rec.get(IMAGE_FILE_FIELD) or rec.get(FILENAME_FIELD, '')
        lines.append(f"  DBF raw={raw!r:50s}  norm={_normalise_filename(raw)!r}")
    lines.append('── OCR filename samples (raw → normalised) ──')
    for res in ocr_results[:8]:
        raw  = res.get('file_name', '')
        lines.append(f"  OCR raw={raw!r:50s}  norm={_normalise_filename(raw)!r}")
    return lines


# ---------------------------------------------------------------------------
# ── CLI QUICK-TEST ────────────────────────────────────────────────────────
if __name__ == '__main__':
    import sys, json

    if len(sys.argv) < 2:
        print('Usage: python dbf_handler.py <path.dbf> [ocr.json]')
        sys.exit(0)

    recs, fnames, summary = load_dbf_for_display(sys.argv[1])
    print(summary)
    for r in recs[:3]:
        print(' ', {k: v for k, v in r.items() if k in
                    (IMAGE_FILE_FIELD, FILENAME_FIELD, DRAWER_FIELD,
                     FILE_MARK_FIELD, OPR_NO_FIELD)})

    if len(sys.argv) < 3:
        sys.exit(0)

    with open(sys.argv[2], encoding='utf-8') as f:
        ocr = json.load(f)

    for line in diagnose_match(recs, ocr):
        print(line)

    updated, matched, unmatched = merge_ocr_into_dbf_records(recs, ocr)
    print(f'\nMatched: {matched}  Unmatched: {unmatched}')