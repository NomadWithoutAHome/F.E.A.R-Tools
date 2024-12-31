import os
import sys
import struct
import zlib
import argparse
import string
import re
from pathlib import Path
from typing import Optional

# Constants for compression methods
COM_METHOD_RAW = 0
COM_METHOD_ZLIB = 9

# Pre-compile struct formats for better performance
HEADER_STRUCT = struct.Struct('<' + 'I' * 12)  # 12 DWORDs
FILE_ENTRY_STRUCT = struct.Struct('<' + 'I' * 8)  # 8 DWORDs
FOLDER_ENTRY_STRUCT = struct.Struct('<' + 'I' * 4)  # 4 DWORDs
BLOCK_HEADER_STRUCT = struct.Struct('<II')  # For decompression blocks

# Define the header structure
class TArchFileHeader:
    __slots__ = ('Marker', 'Version', 'NameTableSize', 'FolderCount', 'FileCount', 'Unk')
    
    def __init__(self, data: bytes):
        if len(data) != 48:  # 12 DWORDs * 4 bytes
            raise ValueError("Invalid TArchFileHeader size. Expected 48 bytes.")
        unpacked = HEADER_STRUCT.unpack(data)
        self.Marker = unpacked[0]
        self.Version = unpacked[1]
        self.NameTableSize = unpacked[2]
        self.FolderCount = unpacked[3]
        self.FileCount = unpacked[4]
        self.Unk = unpacked[5:12]

# Define the file entry structure
class TArchFileEntry:
    __slots__ = ('NameOffset', 'FileOffset', 'FileOffsetPad', 'ComFileSize', 
                 'ComFileSizePad', 'RawFileSize', 'RawFileSizePad', 'ComMethod')
    
    def __init__(self, data: bytes):
        if len(data) != 32:  # 8 DWORDs * 4 bytes
            raise ValueError("Invalid TArchFileEntry size. Expected 32 bytes.")
        unpacked = FILE_ENTRY_STRUCT.unpack(data)
        self.NameOffset = unpacked[0]
        self.FileOffset = unpacked[1]
        self.FileOffsetPad = unpacked[2]
        self.ComFileSize = unpacked[3]
        self.ComFileSizePad = unpacked[4]
        self.RawFileSize = unpacked[5]
        self.RawFileSizePad = unpacked[6]
        self.ComMethod = unpacked[7]

# Define the folder entry structure
class TArchFolderEntry:
    __slots__ = ('NameOffset', 'Unk1', 'Unk2', 'FileCount')
    
    def __init__(self, data: bytes):
        if len(data) != 16:  # 4 DWORDs * 4 bytes
            raise ValueError("Invalid TArchFolderEntry size. Expected 16 bytes.")
        unpacked = FOLDER_ENTRY_STRUCT.unpack(data)
        self.NameOffset = unpacked[0]
        self.Unk1 = unpacked[1]
        self.Unk2 = unpacked[2]
        self.FileCount = unpacked[3]

def sanitize_filename(name: str) -> str:
    """
    Removes or replaces invalid characters in file and folder names.
    """
    valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
    sanitized = ''.join(c if c in valid_chars else '_' for c in name)
    print(f"Sanitized '{name}' to '{sanitized}'")
    return sanitized

def normalize_path(name: str) -> Path:
    """
    Splits the name on backslashes and forward slashes,
    sanitizes each part, and rejoins them using pathlib.
    """
    parts = re.split(r'[\\/]', name)
    sanitized_parts = [sanitize_filename(part) for part in parts if part]
    normalized = Path(*sanitized_parts) if sanitized_parts else Path()
    print(f"Normalized path: '{name}' to '{normalized}'")
    return normalized

def decompress_zlib_blocks(in_file, out_file, compressed_size: int) -> bool:
    """
    Decompresses data using FEAR2's block-based compression format.
    """
    try:
        total_read = 0
        decompressor = zlib.decompressobj(-15)  # Raw deflate format
        
        while total_read < compressed_size:
            # Read block header
            header = in_file.read(8)
            if len(header) < 8:
                print("Error: Incomplete block header")
                return False

            compressed_size_block, decompressed_size = BLOCK_HEADER_STRUCT.unpack(header)
            total_read += 8

            # Read the compressed data block
            compressed_data = in_file.read(compressed_size_block)
            if len(compressed_data) < compressed_size_block:
                print("Error: Incomplete compressed data block")
                return False
            total_read += compressed_size_block

            # Handle padding
            padding = (4 - (compressed_size_block % 4)) % 4
            if padding:
                in_file.read(padding)
                total_read += padding

            # Check if this is an uncompressed block
            if compressed_size_block == decompressed_size:
                out_file.write(compressed_data)
            else:
                try:
                    # Try decompression with reusable decompressor object
                    decompressed = decompressor.decompress(compressed_data)
                    if len(decompressed) != decompressed_size:
                        print(f"Warning: Decompressed size mismatch: expected {decompressed_size}, got {len(decompressed)}")
                    out_file.write(decompressed)
                except zlib.error as e:
                    print(f"Error: Failed to decompress block: {e}")
                    return False

        return True
    except Exception as e:
        print(f"Error: Decompression error: {e}")
        return False

def get_string_from_table(name_table: bytes, offset: int) -> Path:
    """
    Extracts a null-terminated string from the name table at the given offset.
    """
    if offset >= len(name_table):
        print(f"Warning: Offset {offset} out of range for name table.")
        return Path("unknown")
    end = name_table.find(b'\x00', offset)
    if end == -1:
        end = len(name_table)
    try:
        name = name_table[offset:end].decode('utf-8', errors='ignore')
    except UnicodeDecodeError:
        name = "unknown"
    path = normalize_path(name)
    return path

def archive_extract(file_name: Path, target_folder: Path) -> bool:
    """Extract contents of an archive file."""
    try:
        with open(file_name, 'rb') as infile:
            # Read and parse header
            header_data = infile.read(48)  # 12 DWORDs * 4 bytes
            if len(header_data) < 48:
                print("Error: Incomplete header.")
                return False
            arch_header = TArchFileHeader(header_data)
            print(f"Header - Marker: {arch_header.Marker}, Version: {arch_header.Version}, "
                  f"NameTableSize: {arch_header.NameTableSize}, "
                  f"FolderCount: {arch_header.FolderCount}, FileCount: {arch_header.FileCount}")

            # Read name table
            name_table = infile.read(arch_header.NameTableSize)
            if len(name_table) < arch_header.NameTableSize:
                print("Error: Incomplete name table.")
                return False
            print(f"Read name table of size {arch_header.NameTableSize} bytes.")

            # Read file entries
            arch_file_table = []
            file_entries_data = infile.read(32 * arch_header.FileCount)
            if len(file_entries_data) < 32 * arch_header.FileCount:
                print("Error: Incomplete file entries.")
                return False
            for i in range(arch_header.FileCount):
                entry_data = file_entries_data[i*32:(i+1)*32]
                arch_file_table.append(TArchFileEntry(entry_data))
            print(f"Read {len(arch_file_table)} file entries.")

            # Read folder entries
            arch_folder_table = []
            folder_entries_data = infile.read(16 * arch_header.FolderCount)
            if len(folder_entries_data) < 16 * arch_header.FolderCount:
                print("Error: Incomplete folder entries.")
                return False
            for i in range(arch_header.FolderCount):
                folder_data = folder_entries_data[i*16:(i+1)*16]
                arch_folder_table.append(TArchFolderEntry(folder_data))
            print(f"Read {len(arch_folder_table)} folder entries.")

            # Process folders and files
            return _process_folders_and_files(infile, arch_folder_table, arch_file_table, name_table, target_folder)

    except Exception as e:
        print(f"Error extracting '{file_name}': {e}")
        return False

def _process_folders_and_files(infile, arch_folder_table, arch_file_table, name_table, target_folder) -> bool:
    """Process folders and files from the archive."""
    try:
        file_entry_index = 0
        for folder_index, folder in enumerate(arch_folder_table):
            if folder.FileCount == 0:
                print(f"Folder {folder_index} has no files. Skipping.")
                continue

            folder_name = get_string_from_table(name_table, folder.NameOffset)
            if not folder_name:
                folder_name = Path("unknown_folder")
            out_folder_path = target_folder / folder_name
            print(f"Creating directory: '{out_folder_path}'")
            out_folder_path.mkdir(parents=True, exist_ok=True)

            # Process files in folder
            for _ in range(folder.FileCount):
                if file_entry_index >= len(arch_file_table):
                    print("Error: File entry index out of range.")
                    return False

                if not _process_single_file(infile, arch_file_table[file_entry_index], 
                                         name_table, out_folder_path):
                    return False
                file_entry_index += 1

        return True
    except Exception as e:
        print(f"Error processing folders and files: {e}")
        return False

def _process_single_file(infile, file_entry, name_table, out_folder_path) -> bool:
    """Process a single file from the archive."""
    try:
        file_name = get_string_from_table(name_table, file_entry.NameOffset)
        if not file_name:
            file_name = Path("unknown")

        out_file_path = out_folder_path / file_name
        print(f"Writing file: '{out_file_path}'")

        infile.seek(file_entry.FileOffset)
        out_file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(out_file_path, 'wb') as outfile:
            if file_entry.ComMethod == COM_METHOD_RAW:
                raw_size = file_entry.RawFileSize
                outfile.write(infile.read(raw_size))
                print(f"Extracted raw file: '{out_file_path}'")
                return True
            elif file_entry.ComMethod == COM_METHOD_ZLIB:
                success = decompress_zlib_blocks(infile, outfile, file_entry.ComFileSize)
                if success:
                    print(f"Extracted and decompressed file: '{out_file_path}'")
                else:
                    print(f"Failed to decompress '{out_file_path}'")
                return success
            else:
                print(f"Unsupported compression method {file_entry.ComMethod} for file '{file_name}'")
                return False

    except Exception as e:
        print(f"Error processing file: {e}")
        return False

def archive_batch_extract(source_folder: Path, target_folder: Path, delete_source: bool=False):
    """
    Performs batch extraction of all .arch01 files in the source folder.
    """
    for root, dirs, files in os.walk(source_folder):
        root_path = Path(root)
        for file in files:
            if file.lower().endswith('.arch01'):
                source_file = root_path / file
                relative_path = source_file.parent.relative_to(source_folder)
                target_subfolder = target_folder / relative_path
                target_subfolder.mkdir(parents=True, exist_ok=True)

                print(f'Extracting: {source_file}')
                success = archive_extract(source_file, target_subfolder)
                if success:
                    print(f'Extraction successful: {source_file}')
                    if delete_source:
                        try:
                            source_file.unlink()
                            print(f'Deleted source file: {source_file}')
                        except Exception as del_e:
                            print(f"Failed to delete '{source_file}': {del_e}")
                else:
                    print(f'Extraction failed: {source_file}')


def main():
    parser = argparse.ArgumentParser(
        description='ARCH Extractor v0.1 - Made in Python by ChatGPT',
        formatter_class=argparse.RawTextHelpFormatter,
        usage=argparse.SUPPRESS)  # Suppress the default usage message

    parser.add_argument('mode', nargs='?', help='Mode of operation: batch or extract single file')
    parser.add_argument('source', nargs='?', help='Source file or folder')
    parser.add_argument('target', nargs='?', help='Target folder')
    parser.add_argument('-d', '--delete', action='store_true', help='Delete source files after extraction')

    args = parser.parse_args()

    if not args.mode:
        print('ARCH Extractor v0.2')
        print('Made in Python by Nomadwithoutahome')
        print('\nUsage: ArchExtractor.py [-h] [-d] [mode] [source] [target]\n')
        print('positional arguments:')
        print('  mode          Mode of operation: batch or extract single file')
        print('  source        Source file or folder')
        print('  target        Target folder\n')
        print('options:')
        print('  -h, --help    show this help message and exit')
        print('  -d, --delete  Delete source files after extraction')
        sys.exit(0)

    delete_source = args.delete

    if args.mode.lower() == 'batch':
        if not args.source or not args.target:
            print('Batch mode requires source and target folders.')
            print('\nUsage: ArchExtractor.py batch source_folder target_folder [-d]')
            sys.exit(0)

        source_folder = Path(args.source)
        if not source_folder.exists():
            print(f'Source folder not found: {source_folder}')
            sys.exit(0)

        target_folder = Path(args.target)
        print('Extracting .arch01 files started...')
        print('--------------------------------')
        archive_batch_extract(source_folder, target_folder, delete_source)
        print('--------------------------------')
        print('Extracting .arch01 files finished...')
    else:
        # Single file extraction
        source_file = Path(args.mode)
        target_folder = Path(args.source) if args.source else source_file.parent
        if not source_file.exists():
            print('Input file not found or file was not specified!')
            print('\nUsage: ArchExtractor.py input.arch01 output_folder [-d]')
            sys.exit(0)
        source_ext = source_file.suffix.lower()
        if source_ext == '.arch01':
            print(f'Extracting: {source_file}')
            success = archive_extract(source_file, target_folder)
            if success:
                print('Extracting finished...')
                if delete_source:
                    try:
                        source_file.unlink()
                        print(f'Deleted source file: {source_file}')
                    except Exception as del_e:
                        print(f"Failed to delete '{source_file}': {del_e}")
            else:
                print('Extracting failed!')
        else:
            print(f'Wrong file extension: {source_ext}')
            print('\nUsage: ArchExtractor.py input.arch01 output_folder [-d]')
            sys.exit(0)


if __name__ == '__main__':
    main()