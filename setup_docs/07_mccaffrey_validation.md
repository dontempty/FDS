# 7. McCaffrey_Plume Validation 워크플로

NIST의 McCaffrey 1979 부력 확산화염 실험을 검증하는 20개 케이스(5 화재크기 × 4 격자해상도)를 본 서버에서 실행하고 결과를 자동 분류한다.

## 7.1 케이스 구조

`fds/Validation/McCaffrey_Plume/FDS_Input_Files/` 안에 20개 `.fds` 인풋:

| 화재 크기 | 격자 (`_5`/`_11`/`_21`/`_45`) | MPI 랭크 |
|---|---|---|
| 14, 22, 33, 45, 57 kW | 5/11/21/45 (격자 해상도 ↑) | 27 / 27 / 125 / 158 |

`Run_All.sh`(NIST 원본 스크립트)는 `QFDS` 헬퍼를 통해 잡을 던지지만, 본 서버는 자체 sbatch 래퍼 [`run_mccaffrey.sbatch`](../Validation/McCaffrey_Plume/run_mccaffrey.sbatch)로 더 깔끔하게 처리한다.

## 7.2 출력 분류 정책

각 케이스가 수십~수백 개의 출력 파일을 생성하므로, **`Validation/McCaffrey_Plume/Results/`** 아래에 자동으로 분류한다:

```
Results/
├── 14_kW/                                ← 같은 KW 그룹
│   ├── 5/                                ← KW 뒤 숫자(격자 해상도)별
│   │   ├── McCaffrey_14_kW_5.fds
│   │   ├── McCaffrey_14_kW_5.out
│   │   ├── McCaffrey_14_kW_5.smv
│   │   ├── McCaffrey_14_kW_5_hrr.csv
│   │   ├── McCaffrey_14_kW_5_devc.csv
│   │   ├── McCaffrey_14_kW_5_line.csv      (있을 경우)
│   │   ├── McCaffrey_14_kW_5_*.sf, *.bf, …  (모든 슬라이스/바운더리 파일)
│   │   └── …
│   ├── 11/
│   ├── 21/
│   └── 45/
├── 22_kW/{5,11,21,45}/
├── 33_kW/{5,11,21,45}/
├── 45_kW/{5,11,21,45}/
├── 57_kW/{5,11,21,45}/
└── analysis/                             ← 다운로드/비교 분석용 통합 폴더
    ├── hrr/                              모든 *_hrr.csv 한 곳
    │   ├── McCaffrey_14_kW_5_hrr.csv
    │   ├── McCaffrey_14_kW_11_hrr.csv
    │   └── … (총 20개)
    └── line/                             모든 *_line*.csv + *_devc.csv
        ├── McCaffrey_14_kW_5_line.csv
        ├── McCaffrey_14_kW_5_devc.csv
        └── …
```

`analysis/`는 케이스별 폴더의 hrr/line 파일을 **복사**(원본은 케이스 폴더에 그대로 보존)한 것이라, 한 번에 분석/다운로드하기 쉽다.

## 7.3 실행

전체 20개 케이스 제출:
```bash
cd /shared/home/wel1come1234/workspace/fds/Validation/McCaffrey_Plume
./mccaffrey_submit_all.sh
```

부분 제출 (예: `_5` 격자만, 또는 14 kW만):
```bash
./mccaffrey_submit_all.sh _5         # 모든 14/22/33/45/57 kW의 _5 케이스만
./mccaffrey_submit_all.sh 14_kW      # 14 kW의 모든 격자
./mccaffrey_submit_all.sh 14_kW_5    # 단 한 케이스
```

자원 할당 (스크립트 내부에서 자동):
| 격자 | ranks | --nodes | --ntasks |
|---|---|---|---|
| `_5`  | 27  | 1 | 27  |
| `_11` | 27  | 1 | 27  |
| `_21` | 125 | 2 | 125 |
| `_45` | 158 | 3 | 158 |

> ⚠️ **CPU 전용**: `run_mccaffrey.sbatch`는 `#SBATCH --exclude=gpu[01-02]`로 GPU 노드를 제외한다. 본 검증은 GPU 자원이 필요 없고, gpu01/02는 다른 사용자(예: pascal_gpu_*)가 점유 중이거나 점유할 가능성이 있어 cpu01–06만 사용한다.
>
> CPU 노드 사양: 6대 × 64 logical CPU(32 real core × 2 HT) = 384 logical, 245 GB RAM/노드. 6 노드를 모두 동원 가능하므로 가장 무거운 _45 케이스(3 노드)도 동시에 2개까지 돌 수 있다. 나머지는 Slurm 큐에서 대기.

## 7.4 모니터링

```bash
squeue -u $USER -o "%.10i %.20j %.2t %.10M %.6D %R"
# logs/<CASE>.<jobid>.out 의 'Time Step:' 라인을 tail
tail -f logs/McCaffrey_14_kW_5.*.out
```

## 7.5 잡 종료 후

`run_mccaffrey.sbatch` 마지막에서 `*_hrr.csv`, `*_line*.csv`, `*_devc.csv`를 `Results/analysis/{hrr,line}/`로 자동 복사한다. 추가 작업 없음.

다운로드(예시):
```bash
# 모든 결과 묶기
cd /shared/home/wel1come1234/workspace/fds/Validation/McCaffrey_Plume
tar czf McCaffrey_results.tgz Results/

# analysis만 가볍게
tar czf McCaffrey_analysis.tgz Results/analysis/
```

## 7.6 한 케이스만 직접 다시 돌리기

```bash
sbatch --nodes=1 --ntasks=27 \
       --job-name=McCaffrey_22_kW_5 \
       run_mccaffrey.sbatch McCaffrey_22_kW_5
```

기존 `Results/22_kW/5/` 안의 파일은 덮어써진다 (이전 실행 결과 백업하고 싶으면 미리 mv).

## 7.7 핵심 파일

| 경로 | 용도 |
|---|---|
| [run_mccaffrey.sbatch](../Validation/McCaffrey_Plume/run_mccaffrey.sbatch) | 1개 케이스용 sbatch (자동 분류 포함) |
| [mccaffrey_submit_all.sh](../Validation/McCaffrey_Plume/mccaffrey_submit_all.sh) | 20개 일괄 제출 (필터 인자 가능) |
| [Results/](../Validation/McCaffrey_Plume/Results/) | 분류된 결과 트리 |
| [logs/](../Validation/McCaffrey_Plume/logs/) | Slurm stdout/stderr 로그 |
