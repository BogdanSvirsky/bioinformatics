#!/bin/bash
# variant_pipeline.sh

FASTQ="SRR12717711.fastq"        # ваши ONT-риды
REF="GCF_000005845.2_ASM584v2_genomic.fna"
THREADS=12

# 1. FastQC
fastqc -t $THREADS -o qc_report $FASTQ

# 2. Индексируем референс minimap2 (если не сделано ранее)
minimap2 -d ref.mmi $REF

# 3. Картируем (preset map-ont) -> SAM
minimap2 -ax map-ont ref.mmi $FASTQ > aligned.sam

# 4. SAM -> BAM
samtools view -@ $THREADS -bS aligned.sam > aligned.bam

# 5. flagstat + вывод
samtools flagstat -@ $THREADS aligned.bam > flagstat.txt
mapped_line=$(grep "mapped" flagstat.txt)
echo $mapped_line   # напечатает строку с процентом

# 6. Парсинг % mapped (вызов Python-скрипта)
PCT=$(python3 parse_flagstat.py flagstat.txt)
echo "Mapped: ${PCT}%"


# 7. Проверка > 90% и сортировка
if (( $(echo "$PCT > 90" | bc -l) )); then
    echo "OK"
    samtools sort -@ $THREADS -o aligned.sorted.bam aligned.bam
    samtools index aligned.sorted.bam
    freebayes -f $REF aligned.sorted.bam > variants.vcf
    echo "Finished"
else
    echo "not OK"
fi
