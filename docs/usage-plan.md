# Hermes Agent 활용 방안

## 배경

20개+ 프로젝트를 자율주행 인지/계획, VLM, AI Agent 인프라 세 축으로 운영 중.
크로스 프로젝트 허브로 collaboration 프로젝트를 사용하고 있으며, 여러 서버(par02, dgx01, ktl01, ktl02)에서 작업.

현재 반복되는 작업 패턴:
1. 실험 실행 후 결과 문서화 (findings, diary, roadmap 업데이트)
2. 세션 종료 시 collaboration report 작성
3. 실험 config 변경 → 실행 → 평가 사이클
4. 멀티서버 GPU 작업 상태 확인
5. 데이터 파이프라인 관리 (rosbag → perception → VLM → eval)

## 활용 방향

### 1. 공유 스킬 시스템 (구축 완료)

collaboration에 공유 스킬을 두고 모든 프로젝트의 Claude Code 세션에서 참조하는 방식.

| 스킬 | 파일 | 상태 |
|---|---|---|
| experiment-log | `collaboration/docs/shared-skills/experiment-log.md` | 완료 |
| session-report | `collaboration/docs/shared-skills/session-report.md` | 완료 |
| gpu-status | - | 미구현 |
| experiment-config-diff | - | 미구현 |
| pipeline-trigger | - | 미구현 |

**동작 원리**: 스킬은 마크다운 절차서(template)로, 사용자가 트리거하면 Claude Code가 해당 문서를 읽고 절차대로 수행한다. 로그 자동 분석이 아닌 수동 트리거 방식.

**Hermes 스킬과의 차이**: Hermes의 `~/.hermes/skills/`에 있는 스킬은 Hermes Agent 대화에서만 사용 가능. collaboration 공유 스킬은 어떤 프로젝트의 Claude Code 세션에서든 MCP로 참조 가능.

### 2. 실험 자동화 에이전트 (미구현)

Hermes의 cron 스케줄링 + terminal 도구 + Telegram 게이트웨이를 조합한 시나리오.

**가능한 것들:**
- GPU 서버에서 training job을 cron으로 주기 감시 → Telegram으로 알림
- Telegram에서 자연어 명령 → SSH 터미널 백엔드로 원격 GPU 서버 실행
- 배치 추론 완료 감지 → 자동 평가 → 결과 리포트

**세팅 방법:**
```bash
hermes gateway setup          # Telegram 봇 설정
hermes config set terminal.backend ssh
hermes config set terminal.ssh_host <gpu-server>
hermes gateway start           # 게이트웨이 시작
```

### 3. 크로스 프로젝트 지식 허브 (미구현)

Hermes의 persistent memory + FTS5 session search를 활용.

**가능한 것들:**
- 프로젝트별 핵심 설정, 발견사항, 교훈을 Hermes 메모리에 축적
- 과거 세션 검색으로 크로스 프로젝트 질의 해결
- collaboration MCP와 연동하여 프로젝트 간 브리지

### 4. Subagent 병렬 실험 (미구현)

delegate_tool로 여러 subagent를 병렬 실행.

**가능한 것들:**
- VLM 모델 여러 개를 동시에 같은 데이터셋에 평가
- 여러 config 조합의 실험을 병렬 launch 후 결과 취합
- 서버별 작업을 병렬로 분배

### 5. 로그 기반 패턴 자동 탐지 (미구현, 확장 가능)

현재 스킬은 수동 트리거지만, 다음 단계로 확장 가능:

```
여러 프로젝트의 git log + docs/diaries/ 스캔
→ 반복 작업 유형 클러스터링
→ "이 패턴은 스킬로 만들면 좋겠다" 자동 제안
```

## 추가할 공유 스킬 후보

| 스킬 | 설명 | 적용 프로젝트 |
|---|---|---|
| gpu-status | 멀티서버 GPU 사용률 확인, 실행 중 job 리스트 | 모든 프로젝트 |
| experiment-config-diff | 두 실험 config 비교, 차이점 정리 | rtb-vlm, perception, drivestudio |
| rosbag-pipeline | rosbag 토픽 요약, 프레임 추출, 포맷 변환 | rosbag-ingest, perception, openpilot |
| av-eval-report | nuScenes/Waymo 평가 결과 파싱 → 테이블 정리 | perception, OpenPCDet, SparseDrive |
| paper-to-code | 논문 요약 + 기존 프로젝트 관련성 분석 | autoresearch, 모든 AV 프로젝트 |

## 우선순위

1. **지금 바로**: 공유 스킬(experiment-log, session-report)을 실제 프로젝트 세션에서 사용해보고 피드백
2. **단기**: gpu-status, experiment-config-diff 스킬 추가
3. **중기**: Telegram 게이트웨이 세팅하여 실험 모니터링 자동화
4. **장기**: 로그 기반 패턴 탐지, subagent 병렬 실험 워크플로우
