import os
import sys
import struct
from pathlib import Path
from typing import Optional, List, Tuple
from dataclasses import dataclass

# Constants for file markers
TEX_MARKER = struct.unpack('<I', b'TEXR')[0]
DDS_MARKER = struct.unpack('<I', b'DDS ')[0]

# Pre-compile struct formats for better performance
HEADER_STRUCT = struct.Struct('<3I')  # 3 DWORDs for TEX header
MARKER_STRUCT = struct.Struct('<I')  # Single DWORD for markers


@dataclass
class TexHeader:
    """Data class for TEX file header."""
    Marker: int = TEX_MARKER
    Version: int = 1
    FileType: int = 0

    def pack(self) -> bytes:
        """Pack header into bytes."""
        return HEADER_STRUCT.pack(self.Marker, self.Version, self.FileType)


def read_file_header(file_path: Path) -> Optional[bytes]:
    """Read and validate file header."""
    try:
        with open(file_path, 'rb') as f:
            header_data = f.read(12)  # 3 DWORDs
            if len(header_data) < 12:
                print(f"Error: Incomplete header in {file_path}")
                return None
            return header_data
    except Exception as e:
        print(f"Error reading header from {file_path}: {e}")
        return None


def read_file_content(file_path: Path) -> Optional[bytes]:
    """Read entire file content."""
    try:
        with open(file_path, 'rb') as f:
            return f.read()
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
        return None


def write_file_content(file_path: Path, content: bytes) -> bool:
    """Write content to file, creating directories if needed."""
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, 'wb') as f:
            f.write(content)
        return True
    except Exception as e:
        print(f"Error writing file {file_path}: {e}")
        return False


def tex_convert_to_dds(source_file: Path, target_file: Path) -> bool:
    """Convert TEX file to DDS format."""
    try:
        # Read and verify header
        header_data = read_file_header(source_file)
        if not header_data:
            return False

        marker, version, file_type = HEADER_STRUCT.unpack(header_data)
        if marker != TEX_MARKER:
            print(f"Error: Invalid TEX marker in {source_file}")
            return False

        # Read the DDS data
        with open(source_file, 'rb') as f:
            f.seek(12)  # Skip header
            dds_data = f.read()

        # Write DDS file
        return write_file_content(target_file, dds_data)

    except Exception as e:
        print(f"Error converting {source_file} to DDS: {e}")
        return False


def dds_convert_to_tex(source_file: Path, target_file: Path) -> bool:
    """Convert DDS file to TEX format."""
    try:
        # Read and verify DDS content
        content = read_file_content(source_file)
        if not content or len(content) < 4:
            return False

        marker = MARKER_STRUCT.unpack(content[:4])[0]
        if marker != DDS_MARKER:
            print(f"Error: Invalid DDS marker in {source_file}")
            return False

        # Create TEX header and combine with DDS content
        header = TexHeader()
        return write_file_content(target_file, header.pack() + content)

    except Exception as e:
        print(f"Error converting {source_file} to TEX: {e}")
        return False


def process_files_in_directory(source_folder: Path, target_folder: Path, 
                             process_func, source_ext: str, target_ext: str,
                             delete_source: bool = False) -> bool:
    """Generic function to process files in a directory."""
    try:
        success = True
        for item in source_folder.rglob(f'*.{source_ext}'):
            if not item.is_file():
                continue

            # Create corresponding target path
            rel_path = item.relative_to(source_folder)
            target_file = target_folder / rel_path.with_suffix(f'.{target_ext}')

            print(f'Converting: {item}')
            if process_func(item, target_file):
                print('Converting successful')
                if delete_source:
                    try:
                        item.unlink()
                        print(f'Deleted source file: {item}')
                    except Exception as del_e:
                        print(f"Failed to delete '{item}': {del_e}")
                        success = False
            else:
                print('Converting failed')
                success = False

        return success
    except Exception as e:
        print(f"Error during batch conversion: {e}")
        return False


def batch_convert_tex_to_dds(source_folder: Path, target_folder: Path, delete_source: bool = False) -> bool:
    """Batch convert all TEX files in folder to DDS."""
    return process_files_in_directory(source_folder, target_folder, tex_convert_to_dds, 
                                    'tex', 'dds', delete_source)


def batch_convert_dds_to_tex(source_folder: Path, target_folder: Path, delete_source: bool = False) -> bool:
    """Batch convert all DDS files in folder to TEX."""
    return process_files_in_directory(source_folder, target_folder, dds_convert_to_tex, 
                                    'dds', 'tex', delete_source)


def main():
    import argparse

    parser = argparse.ArgumentParser(description='TEX Converter v0.1 - Python port')
    parser.add_argument('-batch', action='store_true', help='Batch conversion mode')
    parser.add_argument('-tex', action='store_true', help='Convert TEX to DDS')
    parser.add_argument('-dds', action='store_true', help='Convert DDS to TEX')
    parser.add_argument('-d', action='store_true', help='Delete source files after conversion')
    parser.add_argument('source', help='Source file or directory')
    parser.add_argument('target', nargs='?', help='Target directory (optional)')

    args = parser.parse_args()

    print('--------------------------------')
    print('TEX Converter v0.1')
    print('Python port by ChatGPT')
    print('--------------------------------')

    source_path = Path(args.source)
    target_path = Path(args.target) if args.target else source_path.parent

    success = True
    if args.batch:
        if args.tex:
            print('Converting tex files started...')
            print('--------------------------------')
            success = batch_convert_tex_to_dds(source_path, target_path, args.d)
            print('--------------------------------')
            print('Converting tex files finished...')
        elif args.dds:
            print('Converting dds files started...')
            print('--------------------------------')
            success = batch_convert_dds_to_tex(source_path, target_path, args.d)
            print('--------------------------------')
            print('Converting dds files finished...')
        else:
            print('Wrong tool usage, parameter -dds or -tex not found')
            success = False
    else:
        if not source_path.exists():
            print('Input file not found!')
            sys.exit(1)

        # Single file conversion
        source_ext = source_path.suffix.lower()
        if source_ext == '.tex':
            target_file = target_path / source_path.with_suffix('.dds').name
            print(f'Converting: {source_path}')
            success = tex_convert_to_dds(source_path, target_file)
            if success:
                print('Converting finished...')
                if args.d:
                    try:
                        source_path.unlink()
                        print(f'Deleted source file: {source_path}')
                    except Exception as del_e:
                        print(f"Failed to delete '{source_path}': {del_e}")
                        success = False
            else:
                print('Converting failed!')
        elif source_ext == '.dds':
            target_file = target_path / source_path.with_suffix('.tex').name
            print(f'Converting: {source_path}')
            success = dds_convert_to_tex(source_path, target_file)
            if success:
                print('Converting finished...')
                if args.d:
                    try:
                        source_path.unlink()
                        print(f'Deleted source file: {source_path}')
                    except Exception as del_e:
                        print(f"Failed to delete '{source_path}': {del_e}")
                        success = False
            else:
                print('Converting failed!')
        else:
            print(f'Wrong file extension: {source_ext}')
            success = False

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()