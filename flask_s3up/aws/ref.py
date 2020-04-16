import enum

class Region(enum.Enum):
    """
    AWS Service Regions

    Reference:
        https://docs.aws.amazon.com/general/latest/gr/rande.html
    Usage:
        Region.SEOUL.value
    """
    OHIO = 'us-east-2'
    VIRGINIA = 'us-east-1'
    CALIFORNIA = 'us-west-1'
    OREGON = 'us-west-2'
    HONGKONG = 'ap-east-1'
    MUMBAI = 'ap-south-1'
    OSAKA = 'ap-northeast-3'
    SEOUL = 'ap-northeast-2'
    SINGAPORE = 'ap-southeast-1'
    SYDNEY = 'ap-southeast-2'
    TOKYO = 'ap-northeast-1'
    CANADA = 'ca-central-1'
    BEIJING = 'cn-north-1'
    NINGXIA = 'cn-northwest-1'
    FRANKFURT = 'eu-central-1'
    IRELAND = 'eu-west-1'
    LONDON = 'eu-west-2'
    PARIS = 'eu-west-3'
    STOCKHOLM = 'eu-north-1'
    SAOPAULO = 'sa-east-1'
    BAHRAIN = 'me-south-1'
