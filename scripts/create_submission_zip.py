import zipfile
import os
from pathlib import Path

def create_zip(source_dir: Path, output_zip: Path):
    exclude_dirs = {
        '.git',
        '.pytest_cache',
        '__pycache__',
        '.venv',
        'venv',
        'env',
        'ENV',
        '.tempmediaStorage'
    }
    exclude_files = {
        '.coverage',
        '.env',
        'yolov8s.pt',
        'store_intelligence.db-journal'
    }

    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_dir):
            # Modify dirs in-place to skip excluded directories
            dirs[:] = [d for d in dirs if d not in exclude_dirs and not d.startswith('.')]
            
            for file in files:
                if file in exclude_files or file.endswith('.pyc') or file.endswith('.pyo') or file.endswith('.pyd'):
                    continue
                
                file_path = Path(root) / file
                relative_path = file_path.relative_to(source_dir)
                
                # Avoid zipping the output zip itself
                if file_path == output_zip:
                    continue
                
                print(f"Adding: {relative_path}")
                zipf.write(file_path, relative_path)

if __name__ == '__main__':
    workspace = Path(r'c:\Users\BIT\Purplle_Hackathon')
    output = workspace / 'purplle_store_intelligence_submission.zip'
    create_zip(workspace, output)
    print(f"\n[SUCCESS] Created zip archive at: {output}")
    print(f"Size: {output.stat().st_size / 1024 / 1024:.2f} MB")
