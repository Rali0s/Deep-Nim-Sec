pip3 install pypdf pandas nltk scikit-learn
pip3 install ebooklib canvas

gcloud config set disable_usage_reporting false

Welcome to the Google Cloud CLI!

To help improve the quality of this product, we collect anonymized usage data
and anonymized stacktraces when crashes are encountered; additional information
is available at <https://cloud.google.com/sdk/usage-statistics>. This data is
handled in accordance with our privacy policy
<https://cloud.google.com/terms/cloud-privacy-notice>. You may choose to opt in this
collection now (by choosing 'Y' at the below prompt), or at any time in the
future by running the following command:

    gcloud config set disable_usage_reporting false

Do you want to help improve the Google Cloud CLI (y/N)?  y


Your current Google Cloud CLI version is: 544.0.0
The latest available version is: 544.0.0

┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                                    Components                                                   │
├───────────────┬──────────────────────────────────────────────────────┬──────────────────────────────┬───────────┤
│     Status    │                         Name                         │              ID              │    Size   │
├───────────────┼──────────────────────────────────────────────────────┼──────────────────────────────┼───────────┤
│ Not Installed │ App Engine Go Extensions                             │ app-engine-go                │   4.5 MiB │
│ Not Installed │ Artifact Registry Go Module Package Helper           │ package-go-module            │   < 1 MiB │
│ Not Installed │ Cloud Bigtable Command Line Tool                     │ cbt                          │  19.8 MiB │
│ Not Installed │ Cloud Bigtable Emulator                              │ bigtable                     │   8.1 MiB │
│ Not Installed │ Cloud Datastore Emulator                             │ cloud-datastore-emulator     │  36.2 MiB │
│ Not Installed │ Cloud Firestore Emulator                             │ cloud-firestore-emulator     │  54.3 MiB │
│ Not Installed │ Cloud Pub/Sub Emulator                               │ pubsub-emulator              │  49.8 MiB │
│ Not Installed │ Cloud Run Proxy                                      │ cloud-run-proxy              │  11.3 MiB │
│ Not Installed │ Cloud SQL Proxy v2                                   │ cloud-sql-proxy              │  14.6 MiB │
│ Not Installed │ Google Container Registry's Docker credential helper │ docker-credential-gcr        │           │
│ Not Installed │ Kustomize                                            │ kustomize                    │   7.4 MiB │
│ Not Installed │ Log Streaming                                        │ log-streaming                │  16.0 MiB │
│ Not Installed │ Managed Flink Client                                 │ managed-flink-client         │ 383.4 MiB │
│ Not Installed │ Minikube                                             │ minikube                     │  48.8 MiB │
│ Not Installed │ Nomos CLI                                            │ nomos                        │  35.2 MiB │
│ Not Installed │ On-Demand Scanning API extraction helper             │ local-extract                │  22.4 MiB │
│ Not Installed │ Skaffold                                             │ skaffold                     │  34.1 MiB │
│ Not Installed │ Spanner Cli                                          │ spanner-cli                  │  12.3 MiB │
│ Not Installed │ Terraform Tools                                      │ terraform-tools              │  64.0 MiB │
│ Not Installed │ anthos-auth                                          │ anthos-auth                  │  20.9 MiB │
│ Not Installed │ config-connector                                     │ config-connector             │ 130.7 MiB │
│ Not Installed │ enterprise-certificate-proxy                         │ enterprise-certificate-proxy │   7.6 MiB │
│ Not Installed │ gcloud Alpha Commands                                │ alpha                        │   < 1 MiB │
│ Not Installed │ gcloud Beta Commands                                 │ beta                         │   < 1 MiB │
│ Not Installed │ gcloud app Java Extensions                           │ app-engine-java              │ 232.9 MiB │
│ Not Installed │ gcloud app Python Extensions                         │ app-engine-python            │   3.8 MiB │
│ Not Installed │ gcloud app Python Extensions (Extra Libraries)       │ app-engine-python-extras     │   < 1 MiB │
│ Not Installed │ gke-gcloud-auth-plugin                               │ gke-gcloud-auth-plugin       │   3.3 MiB │
│ Not Installed │ istioctl                                             │ istioctl                     │  26.6 MiB │
│ Not Installed │ kpt                                                  │ kpt                          │  14.5 MiB │
│ Not Installed │ kubectl                                              │ kubectl                      │   < 1 MiB │
│ Not Installed │ kubectl-oidc                                         │ kubectl-oidc                 │  20.9 MiB │
│ Not Installed │ pkg                                                  │ pkg                          │           │
│ Installed     │ BigQuery Command Line Tool                           │ bq                           │   1.8 MiB │
│ Installed     │ Cloud Storage Command Line Tool                      │ gsutil                       │  12.4 MiB │
│ Installed     │ Google Cloud CLI Core Libraries                      │ core                         │  22.8 MiB │
│ Installed     │ Google Cloud CRC32C Hash Tool                        │ gcloud-crc32c                │   1.4 MiB │
└───────────────┴──────────────────────────────────────────────────────┴──────────────────────────────┴───────────┘
To install or remove components at your current Google Cloud CLI version [544.0.0], run:
  $ gcloud components install COMPONENT_ID
  $ gcloud components remove COMPONENT_ID

To update your Google Cloud CLI installation to the latest version [544.0.0], run:
  $ gcloud components update


Modify profile to update your $PATH and enable shell command completion?

Example runs
1) Parse TXT + Excel, include MITRE techniques (acronym codes), keep dupes for max recall, write family map:
python3 txt_excel_parser.py \
  --in_dir "/Users/proteu5/Documents/deep/Deep-NIM/Data-Sets" \
  --out "/Users/proteu5/Documents/deep/Deep-NIM/Data-Sets/out_all.csv" \
  --family_map_out "/Users/proteu5/Documents/deep/Deep-NIM/Data-Sets/family_map.csv" \
  --family_guess --split_strategy hybrid --allow_dupes --prefix_code_with_file \
  --min_len 20 --max_len 800 --verbose --sample_output 3
2) Prefer MITRE Technique IDs (T####), limit big sheets to 20k rows × 30 cols:
python3 txt_excel_parser.py \
  --in_dir "/Users/proteu5/Documents/deep/Deep-NIM/Data-Sets" \
  --out "/Users/proteu5/Documents/deep/Deep-NIM/Data-Sets/out_all.csv" \
  --family_map_out "/Users/proteu5/Documents/deep/Deep-NIM/Data-Sets/family_map.csv" \
  --mitre_code techid --excel_max_rows 20000 --excel_max_cols 30 \
  --family_guess --split_strategy hybrid --allow_dupes --prefix_code_with_file \
  --min_len 15 --max_len 900 --verbose
3) Only parse specific Excel sheets (e.g., names containing “controls” or “requirements”):
python3 txt_excel_parser.py \
  --in_dir "/Users/proteu5/Documents/deep/Deep-NIM/Data-Sets" \
  --out "/Users/proteu5/Documents/deep/Deep-NIM/Data-Sets/out_filtered.csv" \
  --family_map_out "/Users/proteu5/Documents/deep/Deep-NIM/Data-Sets/family_map_filtered.csv" \
  --excel_sheet_filter "(controls|requirements)" \
  --family_guess --split_strategy sentence --verbose