import inquirer
import os
from pyfiglet import figlet_format
import recon
import interactive_filter
import summarizer
import anomalies
import append
import clean_up
import credit_debit_splitter

def display_banner():
    title = figlet_format("IT Audit Tools")
    print(title)

def main_menu():
    questions = [
        inquirer.List(
            "choice",
            message="Select an option:",
            choices=["Anomaly Detection", "Interactive Filter", "Reconcile Data", "Append Data","Summarize Data", "Clean Up","Credit/Debit Splitter","Exit"],
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
        elif choice == "Clean Up":
            clean_up.main()
        elif choice == "Credit/Debit Splitter":
            credit_debit_splitter.main()
        elif choice == "Exit":
            print("Exiting...")
            break

if __name__ == "__main__":
    main()