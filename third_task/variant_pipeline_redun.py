import re
import os
from redun import task, File
from redun.scripting import script

# ----------------------------------------------------------------------
# Индексирование референса minimap2
# ----------------------------------------------------------------------


@task()
def index_reference(ref_fasta: File) -> dict:
    """Создаёт minimap2 индекс (.mmi)."""
    idx = os.path.splitext(ref_fasta.path)[0] + ".mmi"

    return script(
        f"""

        minimap2 -d {idx} {ref_fasta.path}
        """,
        inputs=[ref_fasta],
        outputs={"index": File(idx).stage()},
    )

# ----------------------------------------------------------------------
# FastQC
# ----------------------------------------------------------------------


@task()
def run_fastqc(fastq: File, output_dir: str) -> File:
    """Запуск FastQC, результат помещается в output_dir."""
    os.makedirs(output_dir, exist_ok=True)
    return script(
        f"""
        fastqc -o {output_dir} {fastq.path}
        """,
        inputs=[fastq],

        outputs={
            "qc_html": File(
                os.path.join(
                    output_dir,
                    fastq.basename().replace(
                        ".fastq",
                        "_fastqc.html"))).stage()},
    )

# ----------------------------------------------------------------------
# Картирование minimap2
# ----------------------------------------------------------------------


@task()
def align_ont(fastq: File, ref_index: dict) -> File:
    """Картирует ONT риды --> SAM."""
    sam = fastq.basename().replace(".fastq", ".sam")
    idx_file = ref_index["index"]
    return script(
        f"""
        minimap2 -ax map-ont -t 4 {idx_file.path} {fastq.path} > {sam}
        """,
        inputs=[fastq, idx_file],
        outputs={"alignment": File(sam).stage()},
    )["alignment"]

# ----------------------------------------------------------------------

# SAM → BAM
# ----------------------------------------------------------------------


@task()
def sam_to_bam(sam_file: File) -> File:
    bam = sam_file.path.replace(".sam", ".bam")
    return script(
        f"""
        samtools view -bS -@ 4 {sam_file.path} > {bam}
        """,
        inputs=[sam_file],
        outputs={"bam": File(bam).stage()},
    )["bam"]

# ----------------------------------------------------------------------
# Samtools flagstat
# ----------------------------------------------------------------------


@task()
def flagstat(bam_file: File) -> dict:
    flagstat_file = bam_file.path + ".flagstat"
    script(
        f"""
        samtools flagstat -@ 4 {bam_file.path} > {flagstat_file}

        """,
        inputs=[bam_file],

        outputs={"flagstat": File(flagstat_file).stage()},

    )
    return {"flagstat": flagstat_file}


# ----------------------------------------------------------------------
# Парсинг процента картированных ридов
# ----------------------------------------------------------------------
@task()
def parse_mapped_pct(flagstat_obj: dict) -> float:
    path = flagstat_obj["flagstat"]

    with open(path) as f:
        for line in f:
            if "mapped (" in line:
                m = re.search(r'\((\d+\.?\d*)%', line)
                if m:
                    return float(m.group(1))
    return 0.0

# ----------------------------------------------------------------------

# Проверка качества и запись статуса

# ----------------------------------------------------------------------


@task()
def quality_check(mapped_pct: float) -> str:
    status = "OK" if mapped_pct > 90 else "not OK"
    out_file = "quality_status.txt"

    with open(out_file, "w") as f:
        f.write(status + "\n")
    script(  # чтобы redun засчитал файл как артефакт
        "true",
        outputs={"status_file": File(out_file).stage()},
    )
    return status

# ----------------------------------------------------------------------
# Сортировка BAM
# ----------------------------------------------------------------------


@task()
def sort_bam(bam_file: File) -> File:
    sorted_bam = bam_file.path.replace(".bam", ".sorted.bam")
    script(
        f"""
        samtools sort -@ 4 -o {sorted_bam} {bam_file.path}

        samtools index {sorted_bam}
        """,
        inputs=[bam_file],
        outputs={
            "sorted_bam": File(sorted_bam).stage(),
            "sorted_bai": File(sorted_bam + ".bai").stage(),
        },
    )
    return File(sorted_bam)

# ----------------------------------------------------------------------
# Коллинг вариантов freebayes
# ----------------------------------------------------------------------


@task()
def call_variants(sorted_bam: File, ref_fasta: File) -> File:
    vcf = sorted_bam.path.replace(".sorted.bam", ".vcf")
    script(
        f"""
        freebayes -f {ref_fasta.path} {sorted_bam.path} > {vcf}
        """,
        inputs=[sorted_bam, ref_fasta],
        outputs={"vcf": File(vcf).stage()},
    )
    return File(vcf)

# ----------------------------------------------------------------------
# Главная сборочная задача
# ----------------------------------------------------------------------


@task()
def pipeline(
    fastq: File,
    ref_fasta: File,
    output_dir: str = "results",
    qc_dir: str = "qc_reports",
) -> dict:
    # Индексация референса
    ref_idx = index_reference(ref_fasta)

    # FastQC
    run_fastqc(fastq, qc_dir)

    # Картирование
    sam = align_ont(fastq, ref_idx)

    # BAM
    bam = sam_to_bam(sam)

    # flagstat
    flag_results = flagstat(bam)
    mapped = parse_mapped_pct(flag_results)

    # Контроль качества
    status = quality_check(mapped)

    # Сортировка, если всё хорошо (условный шаг можно реализовать через if, но redun пока не поддерживает условное выполнение задач на уровне графа. Здесь мы сортируем всегда,
    # но можно было бы сделать ветвление через Python-код в главной задаче, используя динамическое создание задач).
    # Показан простой вариант: сортировка и варианты выполняются только при
    # status == "OK"
    if status == "OK":
        sorted_bam = sort_bam(bam)
        vcf = call_variants(sorted_bam, ref_fasta)
    else:
        sorted_bam = None
        vcf = None

    # Собираем и возвращаем информацию

    return {
        "mapped_percent": mapped,
        "quality_status": status,
        "sorted_bam": sorted_bam,
        "vcf": vcf,
        "flagstat": flag_results["flagstat"],
    }

# ----------------------------------------------------------------------


# Точка входа для redun
# ----------------------------------------------------------------------
if __name__ == "__main__":
    # Локальный запуск можно сделать так, но основное управление через redun run
    # В redun используем декоратор @task для main()
    @task()
    def main():
        # Здесь нужно указать файлы – при реальном запуске лучше передавать аргументы через redun.
        # Для примера укажем локальные пути.
        fastq = File("ont_reads.fastq")
        ref = File("GCF_000005845.2_genomic.fna")
        return pipeline(fastq, ref)
