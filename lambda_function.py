import requests
import json
from datetime import datetime
from elevenlabs import ElevenLabs
import boto3
import time
import firebase_admin
from firebase_admin import credentials, firestore, initialize_app
import random
import os

# Filepath for news object creation
# /scripts/news_object_creator.py

# Constants for APIs
PERPLEXITY_API_KEY = os.getenv('PERPLEXITY_API_KEY')
HEYGEN_API_KEY = os.getenv('HEYGEN_API_KEY')
HEYGEN_VIDEO_URL = os.getenv('HEYGEN_VIDEO_URL')
ELEVEN_LABS_API_KEY = os.getenv('ELEVEN_LABS_API_KEY')
ELEVEN_LABS_TTS_URL = os.getenv('ELEVEN_LABS_TTS_URL')


# Initialize Firebase
# Initialize Firebase
if not firebase_admin._apps:
    firebase_cred_path = os.getenv('FIREBASE_CREDENTIALS_PATH')
    cred = credentials.Certificate(firebase_cred_path)
    firebase_app = initialize_app(cred)

db = firestore.client()

# def format_created_time(created_time):
#     """Convert created_time to a readable format."""
#     return datetime.fromisoformat(created_time).strftime("%B %d, %Y at %I:%M:%S %p %Z")

def generate_title(summary_text):
    """Generate title using Perplexity's API."""
    perplexity_endpoint = "https://api.perplexity.ai/chat/completions"
    headers = {"Authorization": f"Bearer {PERPLEXITY_API_KEY}"}
    payload = {
        "model": "llama-3.1-sonar-small-128k-online",
        "messages": [
          {
            "role": "system",
            "content": "Be precise and concise."
          },
          {
            "role": "user",
            "content": "Generate a short 5-10 word title for this news in the form of a simple line without mentioning any introduction or double quotes. The news: " + summary_text
          }
        ],
        "max_tokens": 15000,
        "temperature": 0.2,
        "top_p": 0.9,
        "search_domain_filter": [
          "perplexity.ai"
        ],
        "return_images": False,
        "return_related_questions": False,
        "search_recency_filter": "month",
        "top_k": 0,
        "stream": False,
        "presence_penalty": 0,
        "frequency_penalty": 1
      }
    response = requests.post(perplexity_endpoint, headers=headers, json=payload)
    print(response.json())
    return response.json().get("choices")[0].get("message").get("content")



def generate_video_script(summary_text):
    """Generate a script for the video using Perplexity's API."""
    perplexity_endpoint = "https://api.perplexity.ai/chat/completions"
    headers = {"Authorization": f"Bearer {PERPLEXITY_API_KEY}"}
    payload = {
        "model": "llama-3.1-sonar-small-128k-online",
        "messages": [
          {
            "role": "system",
            "content": "Be creative and artistic."
          },
          {
            "role": "user",
            "content": "Create a 20 second dialog for a single speaker in the form of a simple paragraph without mentioning speaker or double quotes. This should provide an easy to understand text considering every detail in the news. The news:" + summary_text
          }
        ],
        "max_tokens": 15000,
        "temperature": 0.2,
        "top_p": 0.9,
        "search_domain_filter": [
          "perplexity.ai"
        ],
        "return_images": False,
        "return_related_questions": False,
        "search_recency_filter": "month",
        "top_k": 0,
        "stream": False,
        "presence_penalty": 0,
        "frequency_penalty": 1
      }
    response = requests.post(perplexity_endpoint, headers=headers, json=payload)
    print(response.json())
    return response.json().get("choices")[0].get("message").get("content")

def upload_to_s3(file_path, title):
    """Uploads a file to a S3 bucket."""
    try:
        s3 = boto3.client(
            "s3",
            aws_access_key_id="",
            aws_secret_access_key="",
            region_name="ap-south-1",
        )
        file_name = title.replace(" ", "_").lower() + ".mp3"
        # Upload the file without needing explicit ACL if bucket is public
        s3.upload_file(file_path, "finbytes", f"audio/{file_name}")
        # Construct the public URL
        file_url = f"https://finbytes.s3.ap-south-1.amazonaws.com/audio/{file_name}"
        return file_url
    except Exception as e:
        raise Exception(f"Failed to upload to S3: {str(e)}")

def generate_audio(voice_id, script, title):
    """Generate audio from script using Eleven Labs TTS API."""
    client = ElevenLabs(
        api_key="",
    )
    response = client.text_to_speech.convert(
        voice_id=voice_id,
        model_id="eleven_multilingual_v2",
        text=script,
    )
    print(response)
    if response:
        # Save the audio file locally
        output_file_path = "generated_audio.mp3"
        with open(output_file_path, "wb") as file:
            # Iterate through the generator and write each chunk to the file
            for chunk in response:  # This will iterate through the generator and get each chunk of data
                file.write(chunk)  # Write the chunk to the file

        # Upload to S3 without credentials
        audio_url = upload_to_s3(output_file_path, title)
        return audio_url
    else:
        raise Exception(f"Failed to generate audio: {response}")

def generate_video_with_audio(title, template_id, audio, image_url):
    """Generate a video using HeyGen's API with audio."""
    headers = {"X-Api-Key": f"{HEYGEN_API_KEY}"}
    payload = {
        "test": False,
        "caption": True,
        "dimension": {"width": 720, "height": 1280},
        "aspect_ratio": "9:16",
        "template_id": template_id,
        "title": title.replace(" ", "_").lower(),
        "variables": {
            "voice": {
                "name": "voice",
                "type": "audio",
                "properties": {
                    "url": audio,
                    "asset_id": None
                }
            },
            "image": {
                "name": "image",
                "type": "image",
                "properties": {
                    "url": image_url,
                    "asset_id": None,
                    "fit": "none"
                }
            }
        }
    }
    response = requests.post(f"https://api.heygen.com/v2/template/{template_id}/generate", headers=headers, json=payload)
    print(response.json())
    response.raise_for_status()

    # Retrieve the video ID from the response
    video_id = response.json().get("data", {}).get("video_id")
    if not video_id:
        raise ValueError("Failed to create video: No video ID returned.")

    print(f"Video creation initiated with template")
    return video_id


def poll_heygen_video_status(video_id: str):
    url = f"https://api.heygen.com/v1/video_status.get?video_id={video_id}"
    headers = {"X-Api-Key": f"{HEYGEN_API_KEY}",
               "Accept": "application/json"}

    while True:
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        status = response.json().get("data").get("status")
        if status == "completed":
            video_url = response.json().get("data").get("video_url")
            print(f"Video completed! Download it here: {video_url}")
            return video_url
        elif status == "failed":
            error = response.json().get("data").get("error").get("detail")
            raise ValueError(f"Video generation failed. {error}")

        print("Video is still processing... Checking again in 30 seconds.")
        time.sleep(30)  # Wait before checking status again



def create_news_object(input_json):
    """Main function to create the news object."""
    # Parse the input JSON
    created_time = input_json["created_time"]
    # template_id = input_json["templateID"]
    title = input_json["title"]
    summary_text = input_json["summary_text"]
    image_url = input_json["image_url"]

    template_list = [{
        "template_id": "f293f92b29b94735aa6860a016cffcd0",
        "voice_id": "vYENaCJHl4vFKNDYPr8y"
    }, {
        "template_id": "94065d8bfc56432c93675835342faa48",
        "voice_id": "0ZOhGcBopt9S6GBK8tnj"
    }, {
        "template_id": "dfe690b6a371416e998b742ab2574779",
        "voice_id": "Oq0cIHWGcnbOGozOQv0t"
    }, {
        "template_id": "79f5ab6ee28b429da09c679ae06952ab",
        "voice_id": "xMagNCpMgZ83QOEsHNre"
    }, {
        "template_id": "9890ae5d5a4042b1a73cf78df6f07870",
        "voice_id": "6BZyx2XekeeXOkTVn8un"
    }, {
        "template_id": "547c0e58249a452989f1849645fafc51",
        "voice_id": "EaBs7G1VibMrNAuz2Na7"
    }, {
        "template_id": "ab51f3a086ba4329a4c2eb58c9eb1335",
        "voice_id": "IY8nsD2RIP5N4FFQLaT3"
    }]
    # Select a random JSON object
    selected_template = random.choice(template_list)

    # Set variables for further execution
    template_id = selected_template["template_id"]
    voice_id = selected_template["voice_id"]


    # Step 1: Generate title and description
    title, description = title, summary_text

    # Step 3: Generate video script
    # script = generate_video_script(summary_text)

    # Step 4: Generate audio from the script
    audio = generate_audio(voice_id, description, title)

    # Step 5: Generate video using the audio
    video_id = generate_video_with_audio(title, template_id, audio, image_url)

    # Poll for the video status
    print("Waiting for video to be processed...")
    video_url = poll_heygen_video_status(video_id)

    print(f"Your video is ready: {video_url}")
    # firestore_timestamp = Timestamp()
    # firestore_timestamp.FromDatetime(datetime.fromisoformat(input_json["created_time"]))

    # Step 6: Assemble the news object
    news_object = {
        "created_time": datetime.fromisoformat(input_json["created_time"]),
        "description": description,
        "isDeployed": True,
        "likes": [],
        "priority": 4,
        "title": title,
        "video_url": video_url,
    }

    return news_object

def add_to_firebase(news_object):
    """Adds the created news object to Firebase Firestore."""
    try:
        db.collection("news").add(news_object)
    except Exception as e:
        raise Exception(f"Failed to add news to Firebase: {str(e)}")

def lambda_handler(event, context):
    try:
        # Parse input from the API Gateway event
        input_data = json.loads(event['body'])
        
        # Validate input
        required_keys = ["created_time", "title", "summary_text", "image_url"]
        for key in required_keys:
            if key not in input_data:
                return {
                    "statusCode": 400,
                    "body": json.dumps({"error": f"Missing required key: {key}"})
                }
        
        # Create the news object
        news_object = create_news_object(input_data)
        
        # Add news object to Firebase
        add_to_firebase(news_object)
        
        return {
            "statusCode": 200,
            "body": json.dumps({"message": "News object created successfully", "news_object": news_object})
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
