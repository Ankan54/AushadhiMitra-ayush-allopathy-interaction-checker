#!/bin/bash
set -e

REGION="us-east-1"
ROLE_ARN="arn:aws:iam::667736132441:role/LambdaExecutionRole"
LAYER_ARN="arn:aws:lambda:us-east-1:667736132441:layer:psycopg2-layer:1"
RUNTIME="python3.11"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LAMBDA_DIR="$PROJECT_DIR/lambda"

DB_HOST="scm-postgres.c2na6oc62pb7.us-east-1.rds.amazonaws.com"
DB_PORT="5432"
DB_NAME="aushadhimitra"
DB_USER="scm_admin"
DB_PASSWORD="${DB_PASSWORD:?Set DB_PASSWORD environment variable}"
DB_SSL="require"
S3_BUCKET="ausadhi-mitra-667736132441"
TAVILY_SECRET="ausadhi-mitra/tavily-api-key"

DYNAMODB_TABLE="ausadhi-imppat"

ENV_VARS="Variables={DB_HOST=$DB_HOST,DB_PORT=$DB_PORT,DB_NAME=$DB_NAME,DB_USER=$DB_USER,DB_PASSWORD=$DB_PASSWORD,DB_SSL=$DB_SSL,S3_BUCKET=$S3_BUCKET,REGION=$REGION,TAVILY_SECRET_NAME=$TAVILY_SECRET,DYNAMODB_TABLE=$DYNAMODB_TABLE}"

deploy_lambda() {
    local FUNC_NAME="$1"
    local FUNC_DIR="$2"
    local TIMEOUT="${3:-30}"
    local MEMORY="${4:-256}"
    local DESC="$5"

    echo "=============================="
    echo "Deploying: $FUNC_NAME"
    echo "=============================="

    TEMP_DIR=$(mktemp -d)
    ZIP_FILE="$TEMP_DIR/$FUNC_NAME.zip"

    cp "$FUNC_DIR/handler.py" "$TEMP_DIR/"
    cp -r "$LAMBDA_DIR/shared" "$TEMP_DIR/"

    (cd "$TEMP_DIR" && zip -r "$ZIP_FILE" handler.py shared/)

    if aws lambda get-function --function-name "$FUNC_NAME" --region "$REGION" --no-cli-pager >/dev/null 2>&1; then
        EXISTING="yes"
    else
        EXISTING="no"
    fi

    if [ "$EXISTING" = "yes" ]; then
        echo "  Updating existing function..."
        aws lambda update-function-code \
            --function-name "$FUNC_NAME" \
            --zip-file "fileb://$ZIP_FILE" \
            --region "$REGION" \
            --no-cli-pager

        sleep 2

        aws lambda update-function-configuration \
            --function-name "$FUNC_NAME" \
            --timeout "$TIMEOUT" \
            --memory-size "$MEMORY" \
            --environment "$ENV_VARS" \
            --layers "$LAYER_ARN" \
            --region "$REGION" \
            --no-cli-pager
    else
        echo "  Creating new function..."
        aws lambda create-function \
            --function-name "$FUNC_NAME" \
            --runtime "$RUNTIME" \
            --role "$ROLE_ARN" \
            --handler handler.lambda_handler \
            --zip-file "fileb://$ZIP_FILE" \
            --timeout "$TIMEOUT" \
            --memory-size "$MEMORY" \
            --environment "$ENV_VARS" \
            --layers "$LAYER_ARN" \
            --description "$DESC" \
            --region "$REGION" \
            --no-cli-pager
    fi

    rm -rf "$TEMP_DIR"
    echo "  Done: $FUNC_NAME"
    echo ""
}

echo "Deploying AushadhiMitra Lambda Action Groups..."
echo ""

deploy_lambda "ausadhi-check-curated-db" "$LAMBDA_DIR/check_curated_db" 30 256 \
    "AushadhiMitra: Check curated interactions DB"

deploy_lambda "ausadhi-ayush-data" "$LAMBDA_DIR/ayush_data" 30 512 \
    "AushadhiMitra: AYUSH plant data from DynamoDB IMPPAT"

deploy_lambda "ausadhi-allopathy-data" "$LAMBDA_DIR/allopathy_data" 30 256 \
    "AushadhiMitra: Allopathy drug cache in PostgreSQL"

deploy_lambda "ausadhi-web-search" "$LAMBDA_DIR/web_search" 60 256 \
    "AushadhiMitra: Tavily web search for drug data"

deploy_lambda "ausadhi-reasoning-tools" "$LAMBDA_DIR/reasoning_tools" 30 512 \
    "AushadhiMitra: Build KG, severity scoring, response formatting"

deploy_lambda "ausadhi-planner-tools" "$LAMBDA_DIR/planner_tools" 30 256 \
    "AushadhiMitra: Planner agent - substance identification and plan creation"

deploy_lambda "ausadhi-validation-parser" "$LAMBDA_DIR/validation_parser" 30 128 \
    "AushadhiMitra: Parse validation status from Reasoning Agent output"

echo "=============================="
echo "All Lambda functions deployed!"
echo "=============================="

echo ""
echo "Adding Bedrock invoke permissions to all action group Lambdas..."
for FUNC in ausadhi-check-curated-db ausadhi-ayush-data ausadhi-allopathy-data ausadhi-web-search ausadhi-reasoning-tools ausadhi-planner-tools ausadhi-validation-parser; do
    aws lambda add-permission \
        --function-name "$FUNC" \
        --statement-id "AllowBedrockInvoke" \
        --action "lambda:InvokeFunction" \
        --principal "bedrock.amazonaws.com" \
        --region "$REGION" \
        --no-cli-pager 2>/dev/null || echo "  Permission already exists for $FUNC"
done

echo ""
echo "Deployment complete!"
