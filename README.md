# Document Forgery Detection System

Docker-first setup for document forgery detection.

## Prerequisites

- Docker Desktop (Windows/macOS) or Docker Engine + Compose plugin (Linux)
- No local Python or Node installation is required.

## Quick Start

1. Create environment file:

```bash
copy .env.example .env
```

On macOS/Linux:

```bash
cp .env.example .env
```

2. Build and start services:

```bash
docker compose up --build
```

3. Open applications:

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- Blockchain Node: http://localhost:8545

## Local Development without Docker

### Backend

1.  **Navigate to the backend directory:**
    ```bash
    cd backend
    ```
2.  **Create a virtual environment:**
    ```bash
    python -m venv venv
    ```
3.  **Activate the virtual environment:**
    - On Windows:
      ```bash
      .\venv\Scripts\activate
      ```
    - On macOS/Linux:
      ```bash
      source venv/bin/activate
      ```
4.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
5.  **Run the backend server:**
    ```bash
    uvicorn main:app --reload
    ```

### Frontend

1.  **Navigate to the frontend directory:**
    ```bash
    cd frontend
    ```
2.  **Install dependencies:**
    ```bash
    npm install
    ```
3.  **Run the frontend server:**
    ```bash
    npm run dev
    ```

### Blockchain

1.  **Navigate to the blockchain directory:**
    ```bash
    cd blockchain
    ```
2.  **Install dependencies:**
    ```bash
    npm install
    ```
3.  **Run the local blockchain node:**
    ```bash
    npx hardhat node
    ```
4.  **Deploy the smart contract (in a separate terminal):**
    ```bash
    npx hardhat run scripts/deploy-document.ts --network localhost
    ```

## AI Models

The backend utilizes several AI models for forgery detection. Here's a more detailed overview of the models and their architectures.

### 1. Copy-Move Forgery Detector

- **Implementation:** `ai_models/copy_move_detector/forgery_detection/pipeline.py`
- **Usage:** `backend/services/copy_move_service.py`
- **Base Model:** The architecture is based on **ResNet34**.
- **Customization:** The standard ResNet34 model is modified to accept a **6-channel input** instead of the usual 3. These channels consist of the original RGB image data plus 3 channels from an Error Level Analysis (ELA) of the image. The model was trained from scratch on the forgery dataset, not using pre-trained ImageNet weights.
- **Training:** It's trained to classify images as either authentic or forged by learning from the combined RGB and ELA data.

### 2. Doctamper

- **Implementation:** `ai_models/doctamper/forgery_detection/pipeline.py`
- **Usage:** `backend/services/doctamper_service.py`
- **Base Model:** This model uses a **U-Net architecture** with an **EfficientNet-B0** encoder, implemented using the `segmentation-models-pytorch` library.
- **Customization:** The model has two outputs: a segmentation mask to localize tampered regions and a classification output to determine if the document is tampered with at all. The EfficientNet-B0 encoder was not initialized with pre-trained weights.
- **Training:** It is trained on a dataset of tampered and authentic documents to learn how to both classify and localize forgeries.

### 3. Signature Verification

- **Implementation:** `ai_models/ai_detector/signature_verification/pipeline.py`
- **Usage:** `backend/services/signature_verification_service.py`
- **Base Model:** This system uses two models:
  1.  A **YOLO (You Only Look Once)** model to first detect the location of the signature within the document.
  2.  A **ResNet18** model to perform the actual verification on the cropped signature image.
- **Customization:** The ResNet18 model has a custom classification head designed to output a single value indicating whether the signature is genuine or forged.
- **Training:** The ResNet18 model is trained on a dataset of genuine and forged signatures to learn the subtle features that differentiate them.
