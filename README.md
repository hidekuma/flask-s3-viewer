# TL;DR
`FlaskS3Up` is an extension for Flask that adds s3's browsing support to any Flask application.

## Support Python versions and Dependencies
- Python >= 3.7
- boto3 >= 1.12.2

---

## Installation
- Not ready

### Using pip
```python
pip install flask-s3up
```

---

## Usage
Import flask and flask_s3up
```python
from flask_s3up import FlaskS3Up
from flask_s3up.aws.ref import Region
```

Initiailize Flask application and FlaskS3Up.
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
...

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
s3up.register()
```

### Support design templates
| Template namespace | Design               | Description               |
| :-:                | :-:                  | :-:                       |
| base               | Default              | Not designed at all       |
| mdl                | Material Design Lite | [link](https://getmdl.io) |
```python

s3up = FlaskS3Up(
    app,
    namespace=S3UP_NAMESPACE,
    template_namespace='mdl', # Enter template namespace (default: base)
    object_hostname='http://flask-s3up.com',
    config={
        'profile_name': 'PROFILE_NAME',
        'bucket_name': 'S3_BUCKET_NAME'
    }
)
s3up.register()
```

---

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

---

### Full example
You can also configure flask_s3up through AWS IAM credentials.

```python
s3up = FlaskS3Up(
    app, # Flask app
    namespace=S3UP_NAMESPACE, # namespace must be unique
    template_namespace='mdl', # Enter template namespace(default: base)
    object_hostname='http://flask-s3up.com', # file's hostname
    allowed_extensions={}, # allowed extension
    config={ # Bucket configs and else
        'profile_name': 'PROFILE_NAME', # Required
        'bucket_name': 'S3_BUCKET_NAME', # Required
        'access_key': 'AWS_IAM_ACCESS_KEY', # Not necessary, if you configure aws settings, e.g. ~/.aws
        'secret_key': 'AWS_IAM_SECRET_KEY', # Not necessary, if you configure aws settings, e.g. ~/.aws
        'region_name': Region.SEOUL.value, # or input like 'ap-northease-2'
        'endpoint_url': None, # For S3 compatible
        'use_cache': True, # Flask S3Up will cache the list of s3 objects, if you set True
        'cache_dir': '/tmp/flask_s3up', # Where cached files will be written
        'ttl': 86400, # Time To Live
    }
)
```

---

## Customize template with CLI tool
You can customize template.
```bash
flask_s3up -p templates/mdl -t mdl # Get a Material-design-lite template
flask_s3up -p templates/base -t base # Get a base template (not designed at all)
# or flask_s3up -p templates/base

flask_s3up -h # You can see details
```
When you run the command, you can see the `./templates/{template_namespace}` has been created on your repository. then rerun the Flask application.

And you can change template directory if you want.
```bash
# Get a Material-design-lite template to templates/customized directory 
flask_s3up -p templates/customized -t mdl
```

```python
# then change template_namespace. it will be routed to defined directory (templates/customized)
s3up = FlaskS3Up(
    ...
    template_namespace='customized',
    ...
)
```
### 🚨 Caution
The template folder of flask_s3up is fixed as `templates`. so if you change `template_namespace`, it will be routed `{repository}/templates/{defined template_namespace by you}`.

----

## Things to know
### Searching
- Search only working in EN, because of JMESPath.

## TODOs
- error controlls
- mode (api, view)
- presigned url
- semaphore

---

[License](LICENSE)
------------------

not ready
