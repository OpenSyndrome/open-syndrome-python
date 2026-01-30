import csv
import json
import os
from huggingface_hub import list_repo_files, hf_hub_download


REPO_ID = "opensyndrome/case-definitions"
OUTPUT_CSV = "evaluation/dataset_txt_json.csv"


def get_file_pairs():
    """
    Scans the HF repo and pairs .txt files with .json files
    based on the filename (stem).
    """
    print(f"Scanning repository: {REPO_ID}...")
    all_files = list_repo_files(repo_id=REPO_ID, repo_type="dataset")

    # 1. Bucket files by type
    txt_files = {}  # { "measles_india": "path/to/measles_india" }
    json_files = {}  # { "measles_india": "path/to/measles_india.json" }

    for file_path in all_files:
        if file_path.startswith("human_readable/txt/"):
            stem = os.path.splitext(os.path.basename(file_path))[0]
            txt_files[stem] = file_path

        elif file_path.startswith("machine_readable/json/"):
            stem = os.path.splitext(os.path.basename(file_path))[0]
            json_files[stem] = file_path

    # 2. Find intersections (files that exist in both places)
    paired_keys = set(txt_files.keys()) & set(json_files.keys())

    print(f"Found {len(paired_keys)} matching definition pairs.")
    return paired_keys, txt_files, json_files


def generate_csv():
    keys, txt_paths, json_paths = get_file_pairs()

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as csvfile:
        # Define headers matching your promptfoo config {{vars}}
        fieldnames = ["definition_text", "gold_standard_json"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for key in keys:
            print(f"Processing: {key}...")

            try:
                # Download/Cache content from Hugging Face
                txt_local = hf_hub_download(
                    repo_id=REPO_ID, filename=txt_paths[key], repo_type="dataset"
                )
                json_local = hf_hub_download(
                    repo_id=REPO_ID, filename=json_paths[key], repo_type="dataset"
                )

                # Read contents
                with open(txt_local, "r", encoding="utf-8") as f:
                    text_content = f.read().strip()

                with open(json_local, "r", encoding="utf-8") as f:
                    json_content_obj = json.load(f)
                    json_content_str = json.dumps(json_content_obj)

                writer.writerow(
                    {
                        "definition_text": text_content,
                        "gold_standard_json": json_content_str,
                    }
                )

            except Exception as e:
                print(f"Error processing {key}: {e}")

    print(f"\n✅ Successfully generated {OUTPUT_CSV} with {len(keys)} test cases.")


if __name__ == "__main__":
    generate_csv()
