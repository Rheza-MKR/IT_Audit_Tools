import inquirer
import os
from pyfiglet import figlet_format
import search  # Import search.py
import recon   # Import recon.py
import summarizer
import upload

def display_banner():
    """Display ASCII art title and watermark"""
    title = figlet_format("IT Audit Tools")  # Generate ASCII title
    print(title)

def main_menu():
    """Display the main menu using inquirer"""
    questions = [
        inquirer.List(
            "choice",
            message="Select an option:",
            choices=["Search Data", "Reconcile Data", "Summarize Data","Exit"],
        )
    ]
    
    answer = inquirer.prompt(questions)
    return answer["choice"]

def main():
    """Main function to handle user selection"""
    display_banner()
    while True:
        choice = main_menu()
        
        if choice == "Search Data":
            search.main()  # Correctly calls search.py's main function
        elif choice == "Reconcile Data":
            recon.main()  # Correctly calls recon.py's main function
        elif choice == "Summarize Data":
            summarizer.main()
        elif choice == "Upload to Tableau":
            upload.main()
        elif choice == "Exit":
            print("Exiting...")
            break

if __name__ == "__main__":
    main()
