import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { S3Website } from './constructs/s3-website';
import { DeploymentUser } from './constructs/deployment-user';
import { EnvironmentConfig } from './config/dev';

export interface DishaStackProps extends cdk.StackProps {
  readonly config: EnvironmentConfig;
}

export class DishaStack extends cdk.Stack {
  public readonly website: S3Website;
  public readonly deploymentUser: DeploymentUser;

  constructor(scope: Construct, id: string, props: DishaStackProps) {
    super(scope, id, props);

    const { config } = props;

    // Create the S3 + CloudFront website
    this.website = new S3Website(this, 'Website', {
      bucketName: config.bucketName,
      environment: config.environment,
      enableLogging: config.enableLogging,
    });

    // Create IAM user for GitHub Actions deployment
    this.deploymentUser = new DeploymentUser(this, 'DeploymentUser', {
      environment: config.environment,
      bucket: this.website.bucket,
      distribution: this.website.distribution,
    });

    // Stack-level outputs
    new cdk.CfnOutput(this, 'Environment', {
      value: config.environment,
      description: 'Environment name', 
    });

    new cdk.CfnOutput(this, 'WebsiteUrl', {
      value: this.website.distributionUrl,
      description: 'Website URL',
    });

    new cdk.CfnOutput(this, 'S3BucketName', {
      value: this.website.bucket.bucketName,
      description: 'S3 bucket name for deployments',
    });

    new cdk.CfnOutput(this, 'CloudFrontDistributionId', {
      value: this.website.distribution.distributionId,
      description: 'CloudFront distribution ID for cache invalidation',
    });

    new cdk.CfnOutput(this, 'GitHubActionsAccessKeyId', {
      value: this.deploymentUser.accessKey.accessKeyId,
      description: 'Access Key ID for GitHub Actions (add to repository secrets)',
    });

    // Add tags to the entire stack
    cdk.Tags.of(this).add('Project', 'Disha');
    cdk.Tags.of(this).add('Environment', config.environment);
    cdk.Tags.of(this).add('ManagedBy', 'CDK');
    cdk.Tags.of(this).add('Repository', 'disha-career-platform');
  }
}