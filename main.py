import inquirer
import os
from pyfiglet import figlet_format
import recon
import interactive_filter
import summarizer
import anomalies
import append

def display_banner():
    title = figlet_format("IT Audit Tools")
    print(title)

def main_menu():
    questions = [
        inquirer.List(
            "choice",
            message="Select an option:",
            choices=["Anomaly Detection", "Interactive Filter", "Reconcile Data", "Append Data","Summarize Data", "Exit"],
        )
    ]
    answer = inquirer.prompt(questions)
    return answer["choice"]

def main():
    display_banner()
    while True:
        choice = main_menu()
        if choice == "Anomaly Detection":
            anomalies.main()
        elif choice == "Interactive Filter":
            interactive_filter.main()
        elif choice == "Reconcile Data":
            recon.main()
        elif choice == "Append Data":
            append.main()
        elif choice == "Summarize Data":
            summarizer.main()
        elif choice == "Exit":
            print("Exiting...")
            break

if __name__ == "__main__":
    main()