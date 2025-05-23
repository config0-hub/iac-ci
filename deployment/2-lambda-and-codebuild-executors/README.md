#### Overview of Executors (Lambda/Codebuild) for "iac-ci"
This is only needed if you do not have existing executors in AWS. This is typically installed through the IaC platform Config0.  If you have not signed up for Config0, please set up the executors as presented below.

This installation will set up the Lambda function <span style="color:blue;"> "iac-ci" </span> and create the CodeBuild project <span style="color:blue;"> "iac-ci" </span>  for the open-source project of the same name, which provides CI for Infrastructure as Code (IaC). 

```

                              +-----------------+
                              |     Webhook     |
                              +-----------------+
                                      |
                                      v
                          +--------------------------+
                          |     "iac-ci" system      |  
                          +--------------------------+
                                      |
                              Delegate and Execute
                                      |
                                      v
                    +-----------------+-----------------+
                    | CI                                | TF apply/destroy
                    v                                   v
         +-----------------------+           +-----------------------+
         |    Lambda Function    |           |    CodeBuild Project  |
         +-----------------------+           +-----------------------+
```

When the <span style="color:brown;"> "iac-ci" system </span> receives a webhook, it selects an executor to perform the action. Typically, this will be:

* Lambda function/Codebuild project combination <span style="color:blue;"> "config0-iac"</span> (For users who onboarded to Config0)
* Lambda function/Codebuild project combination <span style="color:blue;"> "iac-ci"</span> configured by the Terraform files in this folder.

