from cst.interface import get_calling_app

app = get_calling_app()
app.ReportInformationToWindow("Hello World!")

print("You should now see the message 'Hello World!' in the message window of the active project.")
