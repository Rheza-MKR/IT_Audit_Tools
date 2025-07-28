import inquirer
from anomalies_tools import manual_entry
from anomalies_tools import improper_desc
from anomalies_tools import account_post
from anomalies_tools import log_duplication
from anomalies_tools import groupping_desc

def display_anomalies_menu():
    questions = [
        inquirer.List(
            "task",
            message="Select an anomaly detection task:",
            choices=[
                "Manual Entry Detection",
                "Improper Description Checker",
                "Wrong Account Posting",
                "Log Duplication Checker",
                "Group Description Sum Checker",
                "Back to Main Menu"
            ]
        )
    ]
    return inquirer.prompt(questions)["task"]

def main():
    while True:
        task = display_anomalies_menu()
        if task == "Manual Entry Detection":
            manual_entry.main()
        elif task == "Improper Description Checker":
            improper_desc.main()
        elif task == "Wrong Account Posting":
            account_post.main()
        elif task == "Log Duplication Checker":
            log_duplication.main()
        elif task == "Group Description Sum Checker":
            groupping_desc.main()
        elif task == "Back to Main Menu":
            break

if __name__== "__main__":
    main()