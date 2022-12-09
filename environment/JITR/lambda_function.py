#
# REPLACE THE WHOLE CODE
# WITH THE CODE OF THE
# LAMBDA IN THE WORKSHOP INSTRUCTIONS
#
from __future__ import print_function

print('Loading function')

def lambda_handler(event, context):
    print("event: {}".format(event))
    return {"message": "i just-in-time registration"}
