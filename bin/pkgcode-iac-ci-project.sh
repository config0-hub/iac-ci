export TMP_BUILD_DIR="/tmp/iac-ci-build"
rm -rf $TMP_BUILD_DIR
mkdir -p $TMP_BUILD_DIR || exit 9
cd ../artifacts || exit 9
unzip base.iac-ci-system-lambda.zip -d $TMP_BUILD_DIR || exit 9
cd ..
cp -rp src/* $TMP_BUILD_DIR/ || exit 9
rm -rf /tmp/iac-ci.zip  || exit 9
cd $TMP_BUILD_DIR || exit 9
zip -r /tmp/iac-ci.zip . || exit 9
tar cvfz /tmp/iac-ci.tar.gz . || exit 9
cd .. || exit 9
rm -rf $TMP_BUILD_DIR || exit 9
