import os
import sys
from processor import classify_file, extract_participants

def main():
    data_folder = os.path.join(os.getcwd(), 'data')
    
    if not os.path.exists(data_folder):
        print(f"Data folder not found at: {data_folder}")
        print("Please create a 'data' folder and put your chat files in it.")
        return

    files = [f for f in os.listdir(data_folder) if os.path.isfile(os.path.join(data_folder, f))]
    
    valid_files = []
    
    print("--- Scanning files ---")
    for file_name in files:
        file_path = os.path.join(data_folder, file_name)
        file_type = classify_file(file_path)
        
        if file_type != 'NULL':
            print(f"Found {file_type}: {file_name}")
            valid_files.append((file_name, file_path, file_type))
    
    if not valid_files:
        print("No WhatsApp or Instagram chat files found.")
        return

    final_results = []
    
    print("\n--- Processing Chats ---")
    for file_name, file_path, file_type in valid_files:
        print(f"\nProcessing: {file_name} ({file_type})")
        participants = extract_participants(file_path, file_type)
        
        if not participants:
            print("No participants found (or unable to parse).")
            # We still allow adding it but maybe with no subject? 
            # Implementation choice: if no participants, maybe just auto-skip or set None.
            # Let's treat it as No Subject automatically or let user confirm.
            subject = "None of them"
        else:
            print("Participants found:")
            for idx, p in enumerate(participants):
                print(f"{idx + 1}. {p}")
            
            print(f"{len(participants) + 1}. None of them")
            
            while True:
                try:
                    choice = int(input(f"Select the 'subject' for {file_name} (1-{len(participants) + 1}): "))
                    if 1 <= choice <= len(participants):
                        subject = participants[choice - 1]
                        break
                    elif choice == len(participants) + 1:
                        subject = "None of them"
                        break
                    else:
                        print("Invalid choice. Please try again.")
                except ValueError:
                    print("Invalid input. Please enter a number.")
        
        if subject != "None of them":
            final_results.append((file_name, subject))
            
    print("\n--- Final Report ---")
    print("Files with identified subjects:")
    for fname, subj in final_results:
        print(f"File: {fname} | Subject: {subj}")

if __name__ == "__main__":
    main()
