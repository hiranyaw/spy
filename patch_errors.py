with open('dashboard_server.py', 'r', encoding='utf-8') as f:
    py = f.read()

# Make the monthly endpoint return errors instead of swallowing them
old_monthly = '''                monthly_data.append(summary)
            except Exception as e:
                print(f"Error parsing file {f}: {e}")
                continue'''

new_monthly = '''                monthly_data.append(summary)
            except Exception as e:
                import traceback
                monthly_data.append({"error": str(e), "trace": traceback.format_exc(), "file": f, "source": "error"})
                continue'''

py = py.replace(old_monthly, new_monthly)

with open('dashboard_server.py', 'w', encoding='utf-8') as f:
    f.write(py)

print("Patch applied")
