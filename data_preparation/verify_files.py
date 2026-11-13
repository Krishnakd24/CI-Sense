import os
import csv

def verify_and_list_missing_files(csv_file_path, base_directory, output_report_csv='verification_report.csv'):
    missing_count = 0
    found_count = 0
    
    results = []
    missing_records = []
    
    # Open and read the CSV file
    with open(csv_file_path, mode='r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader, None)  # Skip header (remove this line if your CSV has no header)
        
        for row in reader:
            if len(row) < 2:
                continue
            
            # Assuming Column 1 is the folder name and Column 2 is the XML file path/name
            folder_name = row[0].strip()
            target_file_path = row[1].strip()
            
            # Construct the full path to check
            full_path = os.path.join(base_directory, folder_name, target_file_path)
            
            # Check existence
            exists = os.path.isfile(full_path)
            
            if exists:
                found_count += 1
                status = "FOUND"
            else:
                missing_count += 1
                status = "MISSING"
                # Store missing records to display in console
                missing_records.append((folder_name, target_file_path, full_path))
                
            results.append([folder_name, target_file_path, status, full_path])

    # Save detailed results to a verification report CSV
    with open(output_report_csv, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Folder Name', 'Target XML', 'Status', 'Checked Path'])
        writer.writerows(results)

    # Print summary and list of missing files to the console
    print("=" * 60)
    print(f"VERIFICATION SUMMARY: Found: {found_count} | Missing: {missing_count}")
    print("=" * 60)
    
    if missing_records:
        print("\n--- MISSING FILES (Folder & File Name) ---")
        for folder, file_name, full_path in missing_records:
            print(f"Folder: {folder}  |  File: {file_name}")
            # Uncomment the line below if you want to see the full absolute search path as well:
            # print(f"   -> Checked Path: {full_path}")
    else:
        print("\nGreat news! No missing files found.")
        
    print(f"\nDetailed report saved to: {output_report_csv}")

if __name__ == '__main__':
    # Update these variables with your actual file names/paths
    CSV_FILE = 'your_file_list.csv'  # Replace with your CSV file name
    BASE_DIR = '.'                    # Path to 'failing_logs_XMLS' folder
    
    verify_and_list_missing_files(CSV_FILE, BASE_DIR)