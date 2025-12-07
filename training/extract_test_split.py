import json
import argparse
from datasets import Dataset

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_file", type=str, default="training/data/sft_train.jsonl")
    parser.add_argument("--output_file", type=str, default="training/data/sft_test.jsonl")
    parser.add_argument("--seed", type=int, default=42, help="Must match train.py seed")
    parser.add_argument("--test_size", type=float, default=0.1, help="Must match train.py test_size")
    args = parser.parse_args()

    print(f"Loading data from {args.input_file}...")
    with open(args.input_file, 'r') as f:
        raw_data = [json.loads(line) for line in f]
    
    # Create HF Dataset
    dataset = Dataset.from_list(raw_data)
    
    # Perform the exact same split as train.py
    print(f"Splitting with seed={args.seed}, test_size={args.test_size}...")
    split = dataset.train_test_split(test_size=args.test_size, seed=args.seed)
    test_dataset = split['test']
    
    print(f"Extracted {len(test_dataset)} test samples.")
    
    # Save to JSONL
    print(f"Saving to {args.output_file}...")
    with open(args.output_file, 'w') as f:
        for sample in test_dataset:
            f.write(json.dumps(sample) + "\n")
            
    print("Done.")

if __name__ == "__main__":
    main()

