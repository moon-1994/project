# project
## 🌐 구조

```
terraform-state-automation/
├── backend/                        # 핵심 로직 모듈
│   ├── terraform_backend_minimum.py     # 백엔드 생성
│   ├── terraform_backend_cleaner.py     # 리소스 삭제
│   └── __init__.py
│
├── scripts/                        # 실행용 CLI
│   ├── delete_resources.py         # 백엔드 리소스 삭제 실행
│   ├── create_backend.py           # (추가 예정) 백엔드 리소스 생성 실행
│
├── .github/workflows/
│   └── deploy.yml                  # Terraform 자동 배포 워크플로
│
├── terraform/                      # Terraform 코드 디렉토리
│   ├── backend.tf
│   ├── main.tf
│   └── variables.tf
│
├── requirements.txt               # 의존성 목록
└── README.md
```