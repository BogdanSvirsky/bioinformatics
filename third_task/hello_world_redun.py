from redun import task, File
from redun.scripting import script


@task()
def say_hello(name: str, output_file: str) -> dict:
    """Записывает приветствие в файл."""
    content = f"Hello, {name}!"
    out_path = output_file + "/greeting.txt"
    with open(out_path, "w") as f:
        f.write(content)
    return {"message": content, "file": out_path}


@task()
def main():
    return say_hello("World", ".")
