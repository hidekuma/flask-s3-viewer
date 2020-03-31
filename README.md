# Flask S3Up
Flask S3Up is an extension for Flask that adds s3's browsing support to any Flask application.

## Support Python versions
- python >= 3.7

## Dependencies
- boto3 >= 1.12.2

## Installation
- not ready

### Using pip
```python
pip install flask-s3up
```
## Usage
Import flask and flask_s3up
```python
from flask_s3up import FlaskS3Up
from flask_s3up.aws.ref import Region
```

Initiailize Flask application and Flask S3Up.
```python
# Init Flask
app = Flask(__name__)

# Init Flask S3Up
S3UP_NAMESPACE = 'flask-s3up'
s3up = FlaskS3Up(
    app, # Flask App
    namespace=S3UP_NAMESPACE, # Namespace must be unique
    object_hostname='http://flask-s3up.com', # Hostname, e.g. Cloudfront endpoint
    config={
        'profile_name': 'PROFILE_NAME',
        'bucket_name': 'S3_BUCKET_NAME'
    }
)
s3up.register()
```

The values in the examples above are mandatory. And you can Initiailize another bucket. Moreover you can limit the file extensions that are uploaded, if you want.
```python
# Init another bucket
s3up.add_new_one(
    namespace='another_namespace',
    object_hostname='http://anotherbucket.com',
    allowed_extensions={'jpg', 'jpeg'}, # allowed extension
    config={
        'profile_name': 'PROFILE_NAME',
        'bucket_name': 'S3_BUCKET_NAME'
    }
)
```

### Use caching
S3 is charged per call. Therefore, Flask S3Up supports caching (currently only supports file caching, in-memory database will be supported later).
```python
s3up = FlaskS3Up(
    app, # Flask app
    namespace=S3UP_NAMESPACE, # namespace must be unique
    object_hostname='http://flask-s3up.com', # file's hostname
    allowed_extensions={}, # allowed extension
    config={ # Bucket configs and else
        'profile_name': 'PROFILE_NAME', # Required
        'bucket_name': 'S3_BUCKET_NAME', # Required
        'use_cache': True, # Flask S3Up will cache the list of s3 objects, if you set True
        'cache_dir': '/tmp/flask_s3up', # Where cached files will be written
        'ttl': 86400, # Time To Live
    }
)
```

### Full example
You can also configure flask_s3up through AWS IAM credentials.

```python
s3up = FlaskS3Up(
    app, # Flask app
    namespace=S3UP_NAMESPACE, # namespace must be unique
    object_hostname='http://flask-s3up.com', # file's hostname
    allowed_extensions={}, # allowed extension
    config={ # Bucket configs and else
        'profile_name': 'PROFILE_NAME', # Required
        'bucket_name': 'S3_BUCKET_NAME', # Required
        'access_key': None, # Not necessary, if you configure aws settings, e.g. ~/.aws
        'secret_key': None, # Not necessary, if you configure aws settings, e.g. ~/.aws
        'region_name': Region.SEOUL.value, # or input like 'ap-northease-2'
        'endpoint_url': None, # For S3 compatible
        'use_cache': True, # Flask S3Up will cache the list of s3 objects, if you set True
        'cache_dir': '/tmp/flask_s3up', # Where cached files will be written
        'ttl': 86400, # Time To Live
    }
)
```

## Cli
You can customizing templates.
```bash
flask_s3up -h
flask_s3up -t mdl # Get a Material-design-litre template
flask_s3up -t skeleton # Get a base template (not designed at all)
```
When you run the command, you can see that the `./templates/flask_s3up` folder has been created. After editing the template, restart the Flask application.

----

## Things to know
### Searching
- Search only working in EN, because of JMESPath.

## TODOs
- error controll
- mode (api, view)
- skeleton
- presigned url
- semaphore

[License](LICENSE)
------------------

not ready
