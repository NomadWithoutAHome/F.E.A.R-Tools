import os
import struct
import re
from dataclasses import dataclass
from typing import List, Tuple, Optional

@dataclass
class Section:
    offset: int
    size: int
    data: Optional[bytes] = None

@dataclass
class DSPackHeader:
    magic: str
    version: Tuple[int, int]
    unknown_flags: int
    section_count: int
    sections: List[Section]

class ResourceEntry:
    def __init__(self, name, offset, size, type_id, section_index):
        self.name = name
        self.offset = offset
        self.size = size
        self.type_id = type_id
        self.section_index = section_index
        self.file_extension = self.guess_extension()

    def guess_extension(self):
        """Guess the file extension based on the name."""
        if not self.name:
            return None
        ext_match = re.search(r'\.([a-zA-Z0-9]+)$', self.name.lower())
        return ext_match.group(1) if ext_match else None

class FileSystemEntry:
    def __init__(self, path, source_pack):
        self.path = path
        self.source_pack = source_pack
        self.children = {}
        self.is_file = '.' in path.split('/')[-1]
        self.extension = path.split('.')[-1] if self.is_file else None

    def add_child(self, name):
        if name not in self.children:
            self.children[name] = FileSystemEntry(name, self.source_pack)
        return self.children[name]

class FileSystem:
    def __init__(self):
        self.root = FileSystemEntry("/", None)
        self.extension_stats = {}

    def add_path(self, path, source_pack):
        if not path.startswith('/'):
            path = '/' + path
        
        current = self.root
        parts = [p for p in path.split('/') if p]
        
        for part in parts:
            current = current.add_child(part)
            if current.is_file and current.extension:
                self.extension_stats[current.extension] = self.extension_stats.get(current.extension, 0) + 1

    def print_tree(self, node=None, indent=0, max_depth=5):
        if node is None:
            node = self.root
        
        if indent > max_depth:
            return

        prefix = "  " * indent
        if node.is_file:
            print(f"{prefix}- {node.path} ({node.source_pack})")
        else:
            print(f"{prefix}+ {node.path}/")
            
        for child in sorted(node.children.values(), key=lambda x: (not x.is_file, x.path)):
            self.print_tree(child, indent + 1, max_depth)

    def print_stats(self):
        print("\nFile Extension Statistics:")
        for ext, count in sorted(self.extension_stats.items(), key=lambda x: x[1], reverse=True):
            print(f"{ext}: {count} files")

class MiniPackDecompressor:
    def __init__(self):
        self.input_data = None
        self.output_data = bytearray()
        self.input_pos = 0
        self.output_pos = 0
        
    def decompress(self, compressed_data: bytes, decompressed_size: int) -> bytes:
        """Decompress MiniPack compressed data."""
        self.input_data = compressed_data
        self.output_data = bytearray(decompressed_size)
        self.input_pos = 0
        self.output_pos = 0
        
        while self.input_pos < len(self.input_data):
            # Read control byte
            control = self.input_data[self.input_pos]
            self.input_pos += 1
            
            # Process each bit in control byte
            for bit in range(8):
                if self.input_pos >= len(self.input_data):
                    break
                    
                if (control & (1 << bit)) != 0:
                    # Literal byte
                    self.output_data[self.output_pos] = self.input_data[self.input_pos]
                    self.output_pos += 1
                    self.input_pos += 1
                else:
                    # Back reference
                    if self.input_pos + 1 >= len(self.input_data):
                        break
                        
                    # Read offset and length
                    offset = ((self.input_data[self.input_pos + 1] & 0xF0) << 4) | self.input_data[self.input_pos]
                    length = (self.input_data[self.input_pos + 1] & 0x0F) + 3
                    
                    # Copy bytes from back reference
                    for i in range(length):
                        self.output_data[self.output_pos] = self.output_data[self.output_pos - offset]
                        self.output_pos += 1
                        
                    self.input_pos += 2
                    
                if self.output_pos >= len(self.output_data):
                    break
        
        return bytes(self.output_data)

class DSPackFile:
    def __init__(self, filename):
        self.filename = filename
        self.file = None
        self.sections = []
        self.file_size = 0
        self.magic = None
        self.version = None
        self.flags = None
        self.section_count = 0
        
    def __enter__(self):
        self.file = open(self.filename, 'rb')
        self.file_size = os.path.getsize(self.filename)
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.file:
            self.file.close()

    def validate_offset(self, offset, description=""):
        """Validate that an offset is within the file bounds."""
        if offset < 0 or offset >= self.file_size:
            raise ValueError(f"Invalid offset {description}: {offset} (file size: {self.file_size})")
        return offset

    def validate_length(self, length, description=""):
        """Validate that a length is reasonable."""
        if length < 0:
            raise ValueError(f"Invalid length {description}: {length} (must be non-negative)")
        # Remove file size check since decompressed size can be larger than file size
        return length

    def validate_compressed_length(self, length, description=""):
        """Validate that a compressed length is reasonable."""
        if length < 0 or length > self.file_size:
            raise ValueError(f"Invalid compressed length {description}: {length} (file size: {self.file_size})")
        return length

    def validate_count(self, count, description=""):
        """Validate that a count is reasonable."""
        if count < 0 or count > 100000:  # Arbitrary reasonable limit
            raise ValueError(f"Invalid count {description}: {count}")
        return count
            
    def read_header(self):
        """Read the file header."""
        self.file.seek(0)
        
        # Read magic numbers
        magic1 = self.file.read(4)  # "mgf "
        magic2 = self.file.read(4)  # [8,1,90,90]
        
        if magic1 != b'mgf ' or magic2 != bytes([8, 1, 90, 90]):
            # Try big endian format
            if magic1 != b' fgm' or magic2 != bytes([90, 90, 1, 8]):
                raise ValueError(f"Invalid magic numbers: {magic1.hex()} {magic2.hex()}")
            self.big_endian = True
        else:
            self.big_endian = False
            
        # Skip 4 bytes null padding
        self.file.read(4)
        
        # Read counts and offsets
        if self.big_endian:
            self.num_files = self.validate_count(struct.unpack('>I', self.file.read(4))[0], "num_files")
            self.file_dir_length = self.validate_length(struct.unpack('>I', self.file.read(4))[0], "file_dir_length")
            self.file_dir_offset = self.validate_offset(struct.unpack('>I', self.file.read(4))[0], "file_dir_offset")
            self.num_folders = self.validate_count(struct.unpack('>I', self.file.read(4))[0], "num_folders")
            self.folder_dir_length = self.validate_length(struct.unpack('>I', self.file.read(4))[0], "folder_dir_length")
            self.folder_dir_offset = self.validate_offset(struct.unpack('>I', self.file.read(4))[0], "folder_dir_offset")
            self.names_dir_length = self.validate_length(struct.unpack('>I', self.file.read(4))[0], "names_dir_length")
            self.names_dir_offset = self.validate_offset(struct.unpack('>I', self.file.read(4))[0], "names_dir_offset")
        else:
            self.num_files = self.validate_count(struct.unpack('<I', self.file.read(4))[0], "num_files")
            self.file_dir_length = self.validate_length(struct.unpack('<I', self.file.read(4))[0], "file_dir_length")
            self.file_dir_offset = self.validate_offset(struct.unpack('<I', self.file.read(4))[0], "file_dir_offset")
            self.num_folders = self.validate_count(struct.unpack('<I', self.file.read(4))[0], "num_folders")
            self.folder_dir_length = self.validate_length(struct.unpack('<I', self.file.read(4))[0], "folder_dir_length")
            self.folder_dir_offset = self.validate_offset(struct.unpack('<I', self.file.read(4))[0], "folder_dir_offset")
            self.names_dir_length = self.validate_length(struct.unpack('<I', self.file.read(4))[0], "names_dir_length")
            self.names_dir_offset = self.validate_offset(struct.unpack('<I', self.file.read(4))[0], "names_dir_offset")
        
        print(f"[Directory Info]")
        print(f"  * Files: {self.num_files}")
        print(f"  * Folders: {self.num_folders}")

    def read_names_directory(self):
        """Read the names directory into memory."""
        self.file.seek(self.names_dir_offset)
        self.names_data = self.file.read(self.names_dir_length)
        
    def read_string_at_offset(self, offset):
        """Read a null-terminated string from the names directory at the given offset."""
        if offset >= len(self.names_data):
            return None
        
        end = offset
        while end < len(self.names_data) and self.names_data[end] != 0:
            end += 1
            
        try:
            return self.names_data[offset:end].decode('ascii')
        except:
            return None

    def read_file_entries(self):
        """Read the file entries from the file directory."""
        self.file.seek(self.file_dir_offset)
        self.files = []
        
        for i in range(self.num_files):
            # Read file entry
            if self.big_endian:
                name_offset = self.validate_offset(struct.unpack('>I', self.file.read(4))[0], f"filename_offset_{i}")
                parent_folder = struct.unpack('>i', self.file.read(4))[0]  # Signed for -1
                decompressed_size = self.validate_length(struct.unpack('>I', self.file.read(4))[0], f"decompressed_size_{i}")
                compressed_size = self.validate_compressed_length(struct.unpack('>I', self.file.read(4))[0], f"compressed_size_{i}")
                unknown = struct.unpack('>I', self.file.read(4))[0]
                data_offset = self.validate_offset(struct.unpack('>I', self.file.read(4))[0], f"data_offset_{i}")
            else:
                name_offset = self.validate_offset(struct.unpack('<I', self.file.read(4))[0], f"filename_offset_{i}")
                parent_folder = struct.unpack('<i', self.file.read(4))[0]  # Signed for -1
                decompressed_size = self.validate_length(struct.unpack('<I', self.file.read(4))[0], f"decompressed_size_{i}")
                compressed_size = self.validate_compressed_length(struct.unpack('<I', self.file.read(4))[0], f"compressed_size_{i}")
                unknown = struct.unpack('<I', self.file.read(4))[0]
                data_offset = self.validate_offset(struct.unpack('<I', self.file.read(4))[0], f"data_offset_{i}")
            
            # Validate parent folder reference
            if parent_folder != -1 and (parent_folder < 0 or parent_folder >= self.num_folders):
                raise ValueError(f"Invalid parent folder {parent_folder} for file {i}")
                
            name = self.read_string_at_offset(name_offset)
            if not name:
                raise ValueError(f"Invalid filename at offset {name_offset} for file {i}")
            
            self.files.append({
                'name': name,
                'parent_folder': parent_folder,
                'decompressed_size': decompressed_size,
                'compressed_size': compressed_size,
                'unknown': unknown,
                'data_offset': data_offset
            })

    def read_folder_entries(self):
        """Read the folder entries from the folder directory."""
        self.file.seek(self.folder_dir_offset)
        self.folders = []
        
        for i in range(self.num_folders):
            # Read folder entry
            if self.big_endian:
                name_offset = self.validate_offset(struct.unpack('>I', self.file.read(4))[0], f"foldername_offset_{i}")
                parent_folder = struct.unpack('>i', self.file.read(4))[0]  # Signed for -1
                last_subfolder = struct.unpack('>i', self.file.read(4))[0]  # Signed for -1
                first_subfolder = struct.unpack('>i', self.file.read(4))[0]  # Signed for -1
                first_file = struct.unpack('>i', self.file.read(4))[0]  # Signed for -1
                last_file = struct.unpack('>i', self.file.read(4))[0]  # Signed for -1
            else:
                name_offset = self.validate_offset(struct.unpack('<I', self.file.read(4))[0], f"foldername_offset_{i}")
                parent_folder = struct.unpack('<i', self.file.read(4))[0]  # Signed for -1
                last_subfolder = struct.unpack('<i', self.file.read(4))[0]  # Signed for -1
                first_subfolder = struct.unpack('<i', self.file.read(4))[0]  # Signed for -1
                first_file = struct.unpack('<i', self.file.read(4))[0]  # Signed for -1
                last_file = struct.unpack('<i', self.file.read(4))[0]  # Signed for -1
            
            # Validate references
            if parent_folder != -1 and (parent_folder < 0 or parent_folder >= self.num_folders):
                raise ValueError(f"Invalid parent folder {parent_folder} for folder {i}")
            if first_file != -1 and (first_file < -1 or first_file > self.num_files):
                raise ValueError(f"Invalid first file {first_file} for folder {i}")
            if last_file != -1 and (last_file < -1 or last_file > self.num_files):
                raise ValueError(f"Invalid last file {last_file} for folder {i}")
            
            name = self.read_string_at_offset(name_offset)
            if not name:
                raise ValueError(f"Invalid folder name at offset {name_offset} for folder {i}")
            
            self.folders.append({
                'name': name,
                'parent_folder': parent_folder,
                'last_subfolder': last_subfolder,
                'first_subfolder': first_subfolder,
                'first_file': first_file,
                'last_file': last_file
            })

    def build_folder_paths(self):
        """Build full paths for folders by following parent links."""
        folder_paths = {}
        
        def get_folder_path(index):
            if index in folder_paths:
                return folder_paths[index]
                
            folder = self.folders[index]
            if folder['parent_folder'] == -1:
                path = folder['name']
            else:
                parent_path = get_folder_path(folder['parent_folder'])
                path = f"{parent_path}/{folder['name']}"
            
            folder_paths[index] = path
            return path
            
        for i in range(len(self.folders)):
            folder_paths[i] = get_folder_path(i)
            
        return folder_paths

    def extract_file(self, file_entry):
        """Extract a single file from the archive."""
        if file_entry['compressed_size'] == 0:
            return None, False
        
        # Read the compressed data
        self.file.seek(file_entry['data_offset'])
        compressed_data = self.file.read(file_entry['compressed_size'])
        
        # If the file is not compressed, return it as-is
        if file_entry['compressed_size'] == file_entry['decompressed_size']:
            print("  > File is not compressed")
            return compressed_data, False
        
        # Basic validation check: ensure compressed data is smaller than decompressed size
        if len(compressed_data) >= file_entry['decompressed_size']:
            print("(!!) Invalid compression: compressed size larger than decompressed size")
            return compressed_data, True
        
        # Try to decompress the data
        try:
            decompressor = MiniPackDecompressor()
            data = decompressor.decompress(compressed_data, file_entry['decompressed_size'])
            print(f"  > Successfully decompressed ({file_entry['compressed_size']:,} -> {len(data):,} bytes)")
            return data, False
        except IndexError:
            # For bytearray index out of range errors, extract the file as-is
            print("(!!) Unknown compression format: extracting as-is")
            return compressed_data, True
        except (KeyboardInterrupt, Exception) as e:
            print(f"(!!) Decompression error: {str(e)}")
            return compressed_data, True

    def extract_all_files(self, output_dir):
        """Extract all files to the specified directory."""
        os.makedirs(output_dir, exist_ok=True)
        
        # First build folder paths
        folder_paths = self.build_folder_paths()
        
        # Create folder structure
        for folder_idx, path in folder_paths.items():
            # Convert forward slashes to backslashes and remove leading/trailing slashes
            clean_path = path.strip('/').replace('/', os.path.sep)
            folder_path = os.path.join(output_dir, clean_path)
            os.makedirs(folder_path, exist_ok=True)
        
        # Extract files
        total_files = len(self.files)
        for idx, file_entry in enumerate(self.files, 1):
            if file_entry['parent_folder'] >= 0:
                folder_path = folder_paths[file_entry['parent_folder']].strip('/').replace('/', os.path.sep)
                output_path = os.path.join(output_dir, folder_path, file_entry['name'])
            else:
                output_path = os.path.join(output_dir, file_entry['name'])
                
            print(f"[{idx}/{total_files}] {file_entry['name']}")
            
            data, is_compressed = self.extract_file(file_entry)
            if data:
                if is_compressed:
                    # Add [Compressed] tag before the extension
                    base, ext = os.path.splitext(output_path)
                    output_path = f"{base}[Compressed]{ext}"
                
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, 'wb') as f:
                    f.write(data)
            else:
                print("  - Failed to extract")

    def analyze(self):
        """Analyze the DSPack file."""
        # Read all directory structures
        self.read_header()
        self.read_names_directory()
        self.read_file_entries()
        self.read_folder_entries()
        
        # Build folder paths
        folder_paths = self.build_folder_paths()
        
        # Print analysis
        print(f"\n[Archive Analysis: {os.path.basename(self.filename)}]")
        print(f"=" * 50)
        print(f"Format: {'Big-endian' if self.big_endian else 'Little-endian'}")
        print(f"Files: {len(self.files)}")
        print(f"Folders: {len(self.folders)}")
        
        print("\n[Folder Structure]")
        for i, path in folder_paths.items():
            folder = self.folders[i]
            file_count = folder['last_file'] - folder['first_file'] + 1 if folder['first_file'] >= 0 else 0
            print(f"  {path}/ ({file_count} files)")
        
        print("\n[Sample Files]")
        for file in self.files[:5]:  # Show first 5 files
            comp_ratio = (1 - file['compressed_size'] / file['decompressed_size']) * 100 if file['decompressed_size'] > 0 else 0
            print(f"  * {file['name']}")
            print(f"    Size: {file['decompressed_size']:,} bytes")
            if comp_ratio > 0:
                print(f"    Compression: {comp_ratio:.1f}%")
            print()

def analyze_dspack_files(directory):
    """Analyze all .dsPack files in a directory."""
    print(f"[Scanning] {directory}")
    
    try:
        files = [f for f in os.listdir(directory) if f.lower().endswith('.dspack')]
        if not files:
            print("(!) No .dsPack files found")
            return
            
        print(f"Found {len(files)} .dsPack files")
        
        for filename in files:
            filepath = os.path.join(directory, filename)
            print(f"\n{'=' * 50}")
            try:
                with DSPackFile(filepath) as dspack:
                    dspack.analyze()
            except Exception as e:
                print(f"(!) Error: {str(e)}")
                continue
    except Exception as e:
        print(f"(!) Error scanning directory: {str(e)}")

if __name__ == '__main__':
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description='Analyze and extract files from .dsPack archives')
    parser.add_argument('directory', help='Directory containing .dsPack files')
    parser.add_argument('--extract', '-e', help='Extract files to this directory', metavar='OUTPUT_DIR')
    
    args = parser.parse_args()
    
    try:
        files = os.listdir(args.directory)
        print(f"Found {len(files)} files in directory")
        
        for filename in files:
            if filename.lower().endswith('.dspack'):
                filepath = os.path.join(args.directory, filename)
                print(f"\nProcessing {filepath}")
                try:
                    with DSPackFile(filepath) as dspack:
                        dspack.analyze()
                        if args.extract:
                            output_dir = os.path.join(args.extract, os.path.splitext(filename)[0])
                            print(f"\nExtracting files to {output_dir}")
                            dspack.extract_all_files(output_dir)
                except Exception as e:
                    print(f"Error processing {filepath}: {str(e)}")
                    import traceback
                    traceback.print_exc()
                    continue
    except Exception as e:
        print(f"Error scanning directory: {str(e)}")
        import traceback
        traceback.print_exc() 