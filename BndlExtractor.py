import os
import sys
import struct
import argparse
from pathlib import Path
from typing import Optional, List, Tuple

# Constants
BNDL_MARKER = b'BNDL'  # equivalent to the Delphi version's marker
BNDL_MARKER_INT = struct.unpack('<I', BNDL_MARKER)[0]

# Pre-compile struct formats for better performance
HEADER_STRUCT = struct.Struct('<IIIIII')  # 6 DWORDs
SIZE_STRUCT = struct.Struct('<II')  # 2 DWORDs for file sizes


class BundleHeader:
    __slots__ = ('Marker', 'Version', 'TableSize', 'Unk1', 'Unk2', 'FileCount')
    
    def __init__(self, data: bytes):
        if len(data) != 24:  # 6 DWORDs * 4 bytes
            raise ValueError("Invalid BundleHeader size. Expected 24 bytes.")
        unpacked = HEADER_STRUCT.unpack(data)
        self.Marker = unpacked[0]
        self.Version = unpacked[1]
        self.TableSize = unpacked[2]
        self.Unk1 = unpacked[3]
        self.Unk2 = unpacked[4]
        self.FileCount = unpacked[5]


def read_null_terminated_string(table_buffer: bytes, pos: int) -> Tuple[str, int]:
    """Read a null-terminated string from the buffer and return the string and new position."""
    end = table_buffer.find(b'\x00', pos)
    if end == -1:
        end = len(table_buffer)
    name = table_buffer[pos:end].decode('utf-8', errors='ignore')
    name_size = len(name) + 1  # Include null terminator
    padding = (4 - (name_size % 4)) % 4
    new_pos = pos + name_size + padding
    return name, new_pos


def extract_bundle_file(file_name: Path, target_folder: Path) -> bool:
    """Extract contents of a bundle file."""
    try:
        with open(file_name, 'rb') as infile:
            # Read and validate header
            header_data = infile.read(24)
            if len(header_data) < 24:
                print("Error: Incomplete header.")
                return False

            header = BundleHeader(header_data)

            # Verify BNDL marker
            if header.Marker != BNDL_MARKER_INT:
                print("Error: Invalid BNDL marker")
                return False

            if header.TableSize == 0 or header.FileCount == 0:
                print("Warning: Empty bundle file")
                return True

            # Read name table
            table_buffer = infile.read(header.TableSize)
            if len(table_buffer) < header.TableSize:
                print("Error: Incomplete name table")
                return False

            # Handle Unk2 offset adjustment
            if header.Unk2 != 0:
                data_offset = infile.tell()
                infile.seek(data_offset + (header.Unk2 * 4))

            # Process each file
            table_pos = 0
            for file_index in range(header.FileCount):
                # Read file sizes
                sizes_data = infile.read(8)
                if len(sizes_data) < 8:
                    print(f"Error: Incomplete size data for file {file_index}")
                    return False

                in_size1, in_size2 = SIZE_STRUCT.unpack(sizes_data)
                in_size = in_size2  # Using the second size value as per original code

                # Read file data
                file_data = infile.read(in_size)
                if len(file_data) < in_size:
                    print(f"Error: Incomplete file data for file {file_index}")
                    return False

                # Get filename from table
                out_name, table_pos = read_null_terminated_string(table_buffer, table_pos)

                # Create output file
                out_path = Path(target_folder) / out_name
                out_path.parent.mkdir(parents=True, exist_ok=True)

                print(f"Extracting: {out_path}")
                with open(out_path, 'wb') as outfile:
                    outfile.write(file_data)

        return True
    except Exception as e:
        print(f"Error extracting '{file_name}': {e}")
        return False


def batch_extract_bndl(source_folder: Path, target_folder: Path, delete_source: bool = False) -> bool:
    """Batch extract all BNDL files in a folder."""
    try:
        success = True
        for root, _, files in os.walk(source_folder):
            root_path = Path(root)
            for file in files:
                if not file.lower().endswith('.bndl'):
                    continue
                    
                source_file = root_path / file
                relative_path = source_file.parent.relative_to(source_folder)
                target_subfolder = target_folder / relative_path

                print(f'Extracting: {source_file}')
                if extract_bundle_file(source_file, target_subfolder):
                    print(f'Extraction successful: {source_file}')
                    if delete_source:
                        try:
                            source_file.unlink()
                            print(f'Deleted source file: {source_file}')
                        except Exception as del_e:
                            print(f"Failed to delete '{source_file}': {del_e}")
                            success = False
                else:
                    print(f'Extraction failed: {source_file}')
                    success = False
                    
        return success
    except Exception as e:
        print(f"Error during batch extraction: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='BNDL Extractor v0.1 - Python port by ChatGPT',
        formatter_class=argparse.RawTextHelpFormatter,
        usage=argparse.SUPPRESS)

    parser.add_argument('mode', nargs='?', help='Mode of operation: batch or extract single file')
    parser.add_argument('source', nargs='?', help='Source file or folder')
    parser.add_argument('target', nargs='?', help='Target folder')
    parser.add_argument('-d', '--delete', action='store_true', help='Delete source files after extraction')

    args = parser.parse_args()

    if not args.mode:
        print('BNDL Extractor v0.1')
        print('Python port by ChatGPT')
        print('\nUsage: main.py [-h] [-d] [mode] [source] [target]\n')
        print('positional arguments:')
        print('  mode          Mode of operation: batch or extract single file')
        print('  source        Source file or folder')
        print('  target        Target folder\n')
        print('options:')
        print('  -h, --help    show this help message and exit')
        print('  -d, --delete  Delete source files after extraction')
        return

    delete_source = args.delete

    if args.mode.lower() == 'batch':
        if not args.source or not args.target:
            print('Batch mode requires source and target folders.')
            print('\nUsage: main.py batch source_folder target_folder [-d]')
            return

        source_folder = Path(args.source)
        if not source_folder.exists():
            print(f'Source folder not found: {source_folder}')
            return

        target_folder = Path(args.target)
        print('Extracting bndl files started...')
        print('--------------------------------')
        success = batch_extract_bndl(source_folder, target_folder, delete_source)
        print('--------------------------------')
        print('Extracting bndl files finished...')
        sys.exit(0 if success else 1)
    else:
        # Single file extraction
        source_file = Path(args.mode)
        target_folder = Path(args.source) if args.source else source_file.parent
        if not source_file.exists():
            print('Input file not found or file was not specified!')
            print('\nUsage: main.py input.bndl output_folder [-d]')
            return

        source_ext = source_file.suffix.lower()
        if source_ext == '.bndl':
            print(f'Extracting: {source_file}')
            success = extract_bundle_file(source_file, target_folder)
            if success:
                print('Extracting finished...')
                if delete_source:
                    try:
                        source_file.unlink()
                        print(f'Deleted source file: {source_file}')
                    except Exception as del_e:
                        print(f"Failed to delete '{source_file}': {del_e}")
                sys.exit(0)
            else:
                print('Extracting failed!')
                sys.exit(1)
        else:
            print(f'Wrong file extension: {source_ext}')
            print('\nUsage: main.py input.bndl output_folder [-d]')
            sys.exit(1)


if __name__ == '__main__':
    main()