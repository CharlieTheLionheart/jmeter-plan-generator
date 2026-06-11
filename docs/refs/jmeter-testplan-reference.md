# JMeter Test Plan Component Reference

> Auto-extracted from Apache JMeter User's Manual: Component Reference
>
> This document contains component names, descriptions, and their configurable properties.

## JMeter Test Plan XML Structure Overview

JMeter test plans (`.jmx` files) are XML documents. Each component is represented as an XML element with the following common attributes:

| Attribute | Description |
|-----------|-------------|
| `testname` | Display name of the component in the test tree |
| `enabled` | Whether the component is enabled (`true`/`false`) |
| `guiclass` | GUI class name (internal JMeter class) |
| `testclass` | Test class name (internal JMeter class) |

Element-specific properties are stored as child `stringProp`, `boolProp`, `intProp`, `longProp`, or `elementProp` elements.

## 18.1 Samplers

### FTP Request

Latency is set to the time it takes to login.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this sampler that is shown in the tree. | No |
| Server Name or IP | Domain name or IP address of the FTP server. | Yes |
| Port | Port to use. If this >0, then this specific port is used, otherwise JMeter uses the default FTP port. | No |
| Remote File: | File to retrieve or name of destination file to upload. | Yes |
| Local File: | File to upload, or destination for downloads (defaults to remote file name). | Yes, if uploading (*) |
| Local File Contents: | Provides the contents for the upload, overrides the Local File property. | Yes, if uploading (*) |
| get(RETR) / put(STOR) | Whether to retrieve or upload a file. | Yes |
| Use Binary mode? | Check this to use Binary mode (default ASCII) | Yes |
| Save File in Response? | Whether to store contents of retrieved file in response data. If the mode is ASCII, then the contents will be visible in the View Results Tree. | Yes, if downloading |
| Username | FTP account username. | Usually |
| Password | FTP account password. N.B. This will be visible in the test plan. | Usually |


### HTTP Request

This sampler lets you send an HTTP/HTTPS request to a web server. It also lets you control whether or not JMeter parses HTML files for images and other embedded resources and sends HTTP requests to retrieve them. The following types of embedded resource are retrieved:

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this sampler that is shown in the tree. | No |
| Server | Domain name or IP address of the web server, e.g. www.example.com. [Do not include the http:// prefix.] Note: If the "Host" header is defined in a Header Manager, then this will be used as the virtual host name. Server is required, unless: it is provided by HTTP Request Defaults... | No |
| Port | Port the web server is listening to. Default: 80 | No |
| Connect Timeout | Connection Timeout. Number of milliseconds to wait for a connection to open. | No |
| Response Timeout | Response Timeout. Number of milliseconds to wait for a response. Note that this applies to each wait for a response. If the server response is sent in several chunks, the overall elapsed time may be longer than the timeout. A Duration Assertion can be used to detect responses that ... | No |
| Server (proxy) | Hostname or IP address of a proxy server to perform request. [Do not include the http:// prefix.] | No |
| Port | Port the proxy server is listening to. | No, unless proxy hostname is specified |
| Username | (Optional) username for proxy server. | No |
| Password | (Optional) password for proxy server. (N.B. this stored unencrypted in the test plan) | No |
| Implementation | Java, HttpClient4. If not specified (and not defined by HTTP Request Defaults), the default depends on the value of the JMeter property jmeter.httpsampler, failing that, the HttpClient4 implementation is used. | No |
| Protocol | HTTP, HTTPS or FILE. Default: HTTP | No |
| Method | GET, POST, HEAD, TRACE, OPTIONS, PUT, DELETE, PATCH (not supported for JAVA implementation). With HttpClient4, the following methods related to WebDav are also allowed: COPY, LOCK, MKCOL, MOVE, PROPFIND, PROPPATCH, UNLOCK, REPORT, MKCALENDAR, SEARCH. More methods can be pre-defined for the HttpClien... | Yes |
| Content Encoding | Content encoding to be used (for POST, PUT, PATCH and FILE). This the character encoding to be used, and is not related to the Content-Encoding HTTP header. | No |
| Redirect Automatically | Sets the underlying http protocol handler to automatically follow redirects, so they are not seen by JMeter, and thus will not appear as samples. Should only be used for GET and HEAD requests. The HttpClient sampler will reject attempts to use it for POST or PUT. Warning: see below for information o... | No |
| Follow Redirects | This only has any effect if "Redirect Automatically" is not enabled. If set, the JMeter sampler will check if the response is a redirect and follow it if so. The initial redirect and further responses will appear as additional samples. The URL and data fields of the parent sample will be taken from ... | No |
| Use KeepAlive | JMeter sets the Connection: keep-alive header. This does not work properly with the default HTTP implementation, as connection re-use is not under user-control. It does work with the Apache HttpComponents HttpClient implementations. | No |
| Use multipart/form-data for HTTP POST | Use a multipart/form-data or application/x-www-form-urlencoded post request | No |
| Browser-compatible headers | When using multipart/form-data, this suppresses the Content-Type and Content-Transfer-Encoding headers; only the Content-Disposition header is sent. | No |
| Path | The path to resource (for example, /servlets/myServlet). If the resource requires query string parameters, add them below in the "Send Parameters With the Request" section. As a special case, if the path starts with "http://" or "https://" then this used as the full URL. In this case, the server,... | No |
| Send Parameters With the Request | The query string will be generated from the list of parameters you provide. Each parameter has a name and value, the options to encode the parameter, and an option to include or exclude an equals sign (some applications don't expect an equals sign when the value is the empty string). The query strin... | No |
| File Path: | Name of the file to send. If left blank, JMeter does not send a file, if filled in, JMeter automatically sends the request as a multipart form request. When MIME Type is empty, JMeter will try to guess the MIME type of the given file. If it is a POST or PUT or PATCH request and there is a single fil... | No |
| Parameter name: | Value of the "name" web request parameter. | No |
| MIME Type | MIME type (for example, text/plain). If it is a POST or PUT or PATCH request and either the 'name' attribute (below) are omitted or the request body is constructed from parameter values only, then the value of this field is used as the value of the content-type request header. | No |
| Retrieve All Embedded Resources from HTML Files | Tell JMeter to parse the HTML file and send HTTP/HTTPS requests for all images, Java applets, JavaScript files, CSSs, etc. referenced in the file. See below for more details. | No |
| Save response as MD5 hash? | If this selected, then the response is not stored in the sample result. Instead, the 32 character MD5 hash of the data is calculated and stored instead. This intended for testing large amounts of data. | No |
| URLs must match: | If present, this must be a regular expression that is used to match against any embedded URLs found. So if you only want to download embedded resources from http://example.invalid/, use the expression: http://example\.invalid/.* | No |
| URLs must not match: | If present, this must be a regular expression that is used to filter out any embedded URLs found. So if you don't want to download PNG or SVG files from any source, use the expression: .*\.(?i:svg\|png) | No |
| Use concurrent pool | Use a pool of concurrent connections to get embedded resources. | No |
| Size | Pool size for concurrent connections used to get embedded resources. | No |
| Source address type | *[Only for HTTP Request with HTTPClient implementation]* To distinguish the source address value, select the type of these: Select *IP/Hostname*IP/Hostname to use a specific IP address or a (local) hostname Select *Device*Device to pick the first... | No |
| Source address field | *[Only for HTTP Request with HTTPClient implementation]* This property is used to enable IP Spoofing. It overrides the default local IP address for this sample. The JMeter host must have multiple IP addresses (i.e. IP aliases, network interfaces,... | No |


### JDBC Request

This sampler lets you send a JDBC Request (an SQL query) to a database.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this sampler that is shown in the tree. | No |
| Variable Name of Pool declared in JDBC Connection Configuration | Name of the JMeter variable that the connection pool is bound to. This must agree with the 'Variable Name' field of a JDBC Connection Configuration. | Yes |
| Query Type | Set this according to the statement type: Select Statement Update Statement - use this for Inserts and Deletes as well Callable Statement Prepared Select Statement Prepared Update Statement - use this for Inserts and Deletes as well Commit Rollback Autocommit(false) Autocommit(true) Edit - this shou... | Yes |
| SQL Query | SQL query. Do not enter a trailing semi-colon. There is generally no need to use { and } to enclose Callable statements; however they may be used if the database uses a non-standard syntax. The JDBC driver automatically converts the statement if necessary when it is enclosed in {}. For example: sele... | Yes |
| Parameter values | Comma-separated list of parameter values. Use ]NULL[ to indicate a NULL parameter. (If required, the null string can be changed by defing the property "jdbcsampler.nullmarker".) The list must be enclosed in double-quotes if any of the values contain a comma or double-quote, and any embedded double... | Yes, if a prepared or callable statement has parameters |
| Parameter types | Comma-separated list of SQL parameter types (e.g. INTEGER, DATE, VARCHAR, DOUBLE) or integer values of Constants. Those integer values can be used, when you use custom database types proposed by driver (For example OracleTypes.CURSOR could be represented by its integer value -10). These are defined ... | Yes, if a prepared or callable statement has parameters |
| Variable Names | Comma-separated list of variable names to hold values returned by Select statements, Prepared Select Statements or CallableStatement. Note that when used with CallableStatement, list of variables must be in the same sequence as the OUT parameters returned by the call. If there are less variable name... | No |
| Result Variable Name | If specified, this will create an Object variable containg a list of row maps. Each map contains the column name as the key and the column data as the value. Usage: columnValue = vars.getObject("resultObject").get(0).get("Column Name"); | No |
| Query timeout(s) | Set a timeout in seconds for query, empty value means 0 which is infinite. -1 means don't set any query timeout which might be need for use case or when certain drivers don't support timeout. Defaults to 0. | No |
| Limit ResultSet | Limits the number of rows to iterate through the ResultSet. Empty value means -1, e.g. no limitation, which is also the default. This can help to reduce the amount of data to be fetched from the database via the JDBC driver, but affects all possible options of Handle ResultSet respectively – e.g. in... | No |
| Handle ResultSet | Defines how ResultSet returned from callable statements be handled: Store As String (default) - All variables on Variable Names list are stored as strings, will not iterate through a ResultSet when present on the list. CLOBs will be converted to Strings. BLOBs will be converted to Strings as if they... | No |


### Java Request

This sampler lets you control a java class that implements the org.apache.jmeter.protocol.java.sampler.JavaSamplerClient interface. By writing your own implementation of this interface, you can use JMeter to harness multiple threads, input parameter control, and data collection.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this sampler that is shown in the tree. | No |
| Classname | The specific implementation of the JavaSamplerClient interface to be sampled. | Yes |
| Send Parameters with Request | A list of arguments that will be passed to the sampled class. All arguments are sent as Strings. See below for specific settings. | No |


### LDAP Request

If you are going to send multiple requests to the same LDAP server, consider using an LDAP Request Defaults Configuration Element so you do not have to enter the same information for each LDAP Request.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this sampler that is shown in the tree. | No |
| Server Name or IP | Domain name or IP address of the LDAP server. JMeter assumes the LDAP server is listening on the default port (389). | Yes |
| Port | Port to connect to (default is 389). | Yes |
| root DN | Base DN to use for LDAP operations | Yes |
| Username | LDAP server username. | Usually |
| Password | LDAP server password. (N.B. this stored unencrypted in the test plan) | Usually |
| Entry DN | the name of the context to create or Modify; may not be empty. You have to set the right attributes of the object yourself. So if you want to add cn=apache,ou=test you have to add in the table name and value to cn and apache. | Yes, if User Defined Test and Add Test or Modify Test is selected |
| Delete | the name of the context to Delete; may not be empty | Yes, if User Defined Test and Delete Test is selected |
| Search base | the name of the context or object to search | Yes, if User Defined Test and Search Test is selected |
| Search filter | the filter expression to use for the search; may not be null | Yes, if User Defined Test and Search Test is selected |
| add test | Use these name, value pairs for creation of the new object in the given context | Yes, if User Defined Test and add Test is selected |
| modify test | Use these name, value pairs for modification of the given context object | Yes, if User Defined Test and Modify Test is selected |


### LDAP Extended Request

If you are going to send multiple requests to the same LDAP server, consider using an LDAP Extended Request Defaults Configuration Element so you do not have to enter the same information for each LDAP Request.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this sampler that is shown in the tree. | No |
| Servername | The name (or IP-address) of the LDAP server. | Yes |
| Port | The port number that the LDAP server is listening to. If this omitted JMeter assumes the LDAP server is listening on the default port(389). | No |
| DN | The distinguished name of the base object that will be used for any subsequent operation. It can be used as a starting point for all operations. You cannot start any operation a higher level than this DN! | No |
| Username | Full distinguished name of the user as which you want to bind. | No |
| Password | Password for the above user. If omitted it will result in anonymous bind. If it is incorrect, the sampler will return an error and revert to an anonymous bind. (N.B. this stored unencrypted in the test plan) | No |
| Connection timeout (in milliseconds) | Timeout for connection, if exceed connection will be aborted | No |
| Use Secure LDAP Protocol | Use ldaps:// scheme instead of ldap:// | No |
| Trust All Certificates | Trust all certificates, only used if Use Secure LDAP Protocol is checked | No |


### Access Log Sampler

AccessLogSampler was designed to read access logs and generate http requests. For those not familiar with the access log, it is the log the webserver maintains of every request it accepted. This means every image, CSS file, JavaScript file, html file, …

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this sampler that is shown in the tree. | No |
| Server | Domain name or IP address of the web server. | Yes |
| Protocol | Scheme | No (defaults to http |
| Port | Port the web server is listening to. | No (defaults to 80) |
| Log parser class | The log parser class is responsible for parsing the logs. | Yes (default provided) |
| Filter | The filter class is used to filter out certain lines. | No |
| Location of log file | The location of the access log file. | Yes |


### BeanShell Sampler

This sampler allows you to write a sampler using the BeanShell scripting language.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this sampler that is shown in the tree. The name is stored in the script variable Label | No |
| Reset bsh.Interpreter before each call | If this option is selected, then the interpreter will be recreated for each sample. This may be necessary for some long running scripts. For further information, see Best Practices - BeanShell scripting. | Yes |
| Parameters | Parameters to pass to the BeanShell script. This intended for use with script files; for scripts defined in the GUI, you can use whatever variable and function references you need within the script itself. The parameters are stored in the following variables: Parameters string containg the para... | No |
| Script file | A file containg the BeanShell script to run. The file name is stored in the script variable FileName | No |
| Script | The BeanShell script to run. The return value (if not null) is stored as the sampler result. | Yes (unless script file is provided) |


### JSR223 Sampler

The JSR223 Sampler allows JSR223 script code to be used to perform a sample or some computation required to create/update variables.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this sampler that is shown in the tree. | No |
| Scripting Language | Name of the JSR223 scripting language to be used. There are other languages supported than those that appear in the drop-down list. Others may be available if the appropriate jar is installed in the JMeter lib directory. Notice that some languages such as Velocity may use a different syntax for JSR2... | Yes |
| Script File | Name of a file to be used as a JSR223 script, if a relative file path is used, then it will be relative to directory referenced by "user.dir" System property | No |
| Parameters | List of parameters to be passed to the script file or the script. | No |
| Cache compiled script if available | If checked (advised) and the language used supports Compilable interface (Groovy is one of these, java, beanshell and javascript are not), JMeter will compile the Script and cache it using its MD5 hash as unique cache key | No |
| Script | Script to be passed to JSR223 language | Yes (unless script file is provided) |


### TCP Sampler

The TCP Sampler opens a TCP/IP connection to the specified server. It then sends the text, and waits for a response.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. |  |
| TCPClient classname | Name of the TCPClient class. Defaults to the property tcp.handler, failing that TCPClientImpl. | No |
| ServerName or IP | Name or IP of TCP server | Yes |
| Port Number | Port to be used | Yes |
| Re-use connection | If selected, the connection is kept open. Otherwise it is closed when the data has been read. | Yes |
| Close connection | If selected, the connection will be closed after running the sampler. | Yes |
| SO_LINGER | Enable/disable SO_LINGER with the specified linger time in seconds when a socket is created. If you set "SO_LINGER" value as 0, you may prevent large numbers of sockets sitting around with a TIME_WAIT status. | No |
| End of line(EOL) byte value | Byte value for end of line, set this to a value outside the range -128 to +127 to skip eol checking. You may set this in jmeter.properties file as well with eolByte property. If you set this in TCP Sampler Config and in jmeter.properties file at the same time, the setting value in the TCP Sampler Co... | No |
| Connect Timeout | Connect Timeout (milliseconds, 0 disables). | No |
| Response Timeout | Response Timeout (milliseconds, 0 disables). | No |
| Set NoDelay | See java.net.Socket.setTcpNoDelay(). If selected, this will disable Nagle's algorithm, otherwise Nagle's algorithm will be used. | Yes |
| Text to Send | Text to be sent | Yes |
| Login User | User Name - not used by default implementation | No |
| Password | Password - not used by default implementation (N.B. this stored unencrypted in the test plan) | No |


### JMS Publisher

JMS Publisher will publish messages to a given destination (topic/que). For those not familiar with JMS, it is the J2EE specification for messaging. There are numerous JMS servers on the market and several open source options.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. |  |
| use JNDI properties file | use jndi.properties. Note that the file must be on the classpath - e.g. by updating the user.classpath JMeter property. If this option is not selected, JMeter uses the "JNDI Initial Context Factory" and "Provider URL" fields to create the connection. | Yes |
| JNDI Initial Context Factory | Name of the context factory | No |
| Provider URL | The URL for the JMS provider | Yes, unless using jndi.properties |
| Destination | The message destination (topic or que name) | Yes |
| Setup | The destination setup type. With At startup, the destination name is static (i.e. always same name during the test), with Each sample, the destination name is dynamic and is evaluate at each sample (i.e. the destination name may be a variable) | Yes |
| Authentication | Authentication requirement for the JMS provider | Yes |
| User | User Name | No |
| Password | Password (N.B. this stored unencrypted in the test plan) | No |
| Expiration | The expiration time (in milliseconds) of the message before it becomes obsolete. If you do not specify an expiration time, the default value is 0 (never expires). | No |
| Priority | The priority level of the message. There are ten priority levels from 0 (lowest) to 9 (highest). If you do not specify a priority level, the default level is 4. | No |
| Reconnect on error codes (regex) | Regular expression for JMSException error codes which force reconnection. If empty no reconnection will be done | No |
| Number of samples to aggregate | Number of samples to aggregate | Yes |
| Message source | Where to obtain the message: From File means the referenced file will be read and reused by all samples. If file name changes it is reloaded since JMeter 3.0 Random File from folder specified below means a random file will be selected from folder specified below, this folder must contain either file... | Yes |
| Message type | Text, Map, Object message or Bytes Message | Yes |
| Content encoding | Specify the encoding for reading the message source file: RAW: No variable support from the file and load it with default system charset. DEFAULT: Load file with default system encoding, except for XML which relies on XML prolog. If the file contain variables, they will be processed. Standard charse... | Yes |
| Use non-persistent delivery mode? | Whether to set DeliveryMode.NON_PERSISTENT (defaults to false) | No |
| JMS Properties | The JMS Properties are properties specific for the underlying messaging system. You can setup the name, the value and the class (type) of value. Default type is String. For example: for WebSphere 5.1 web services you will need to set the JMS Property targetService to test webservices through JMS. | No |


### JMS Subscriber

JMS Subscriber will subscribe to messages in a given destination (topic or que). For those not familiar with JMS, it is the J2EE specification for messaging. There are numerous JMS servers on the market and several open source options.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. |  |
| use JNDI properties file | use jndi.properties. Note that the file must be on the classpath - e.g. by updating the user.classpath JMeter property. If this option is not selected, JMeter uses the "JNDI Initial Context Factory" and "Provider URL" fields to create the connection. | Yes |
| JNDI Initial Context Factory | Name of the context factory | No |
| Provider URL | The URL for the JMS provider | No |
| Destination | the message destination (topic or que name) | Yes |
| Durable Subscription ID | The ID to use for a durable subscription. On first use the respective que will automatically be generated by the JMS provider if it does not exist yet. | No |
| Client ID | The Client ID to use when you use a durable subscription. Be sure to add a variable like ${__threadNum} when you have more than one Thread. | No |
| JMS Selector | Message Selector as defined by JMS specification to extract only messages that respect the Selector condition. Syntax uses subpart of SQL 92. | No |
| Setup | The destination setup type. With At startup, the destination name is static (i.e. always same name during the test), with Each sample, the destination name is dynamic and is evaluated at each sample (i.e. the destination name may be a variable) | Yes |
| Authentication | Authentication requirement for the JMS provider | Yes |
| User | User Name | No |
| Password | Password (N.B. this stored unencrypted in the test plan) | No |
| Number of samples to aggregate | number of samples to aggregate | Yes |
| Save response | should the sampler store the response. If not, only the response length is returned. | Yes |
| Timeout | Specify the timeout to be applied, in milliseconds. 0=none. This the overall aggregate timeout, not per sample. | Yes |
| Client | Which client implementation to use. Both of them create connections which can read messages. However they use a different strategy, as described below: MessageConsumer.receive() calls receive() for every requested message. Retains the connection between samples, but does not fetch messages unless th... | Yes |
| Stop between samples? | If selected, then JMeter calls Connection.stop() at the end of each sample (and calls start() before each sample). This may be useful in some cases where multiple samples/threads have connections to the same que. If not selected, JMeter calls Connection.start() at the start of the thread, and does... | Yes |
| Separator | Separator used to separate messages when there is more than one (related to setting Number of samples to aggregate). Note that \n, \r, \t are accepted. | No |
| Reconnect on error codes (regex) | Regular expression for JMSException error codes which force reconnection. If empty no reconnection will be done | No |
| Pause between errors (ms) | Pause in milliseconds that Subscriber will make when an error occurs | No |


### JMS Point-to-Point

This sampler sends and optionally receives JMS Messages through point-to-point connections (ques). It is different from pub/sub messages and is generally used for handling transactions.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. |  |
| QueConnection Factory | The JNDI name of the que connection factory to use for connecting to the messaging system. | Yes |
| JNDI Name Request que | This the JNDI name of the que to which the messages are sent. | Yes |
| JNDI Name Reply que | The JNDI name of the receiving que. If a value is provided here and the communication style is Request Response this que will be monitored for responses to the requests sent. | No |
| Number of samples to aggregate | Number of samples to aggregate. Only applicable for Communication style Read. | Yes |
| JMS Selector | Message Selector as defined by JMS specification to extract only messages that respect the Selector condition. Syntax uses subpart of SQL 92. | No |
| Communication style | The Communication style can be Request Only (also known as Fire and Forget), Request Response, Read, Browse, Clear: Request Only will only send messages and will not monitor replies. As such it can be used to put load on a system. Request Response will send messages and monitor the replies it receiv... | Yes |
| Use alternate fields for message correlation | These check-boxes select the fields which will be used for matching the response message with the original request. Use Request Message Id if selected, the request JMSMessageID will be used, otherwise the request JMSCorrelationID will be used. In the latter case the correlation id must be specified ... | Yes |
| Timeout | The timeout in milliseconds for the reply-messages. If a reply has not been received within the specified time, the specific testcase fails and the specific reply message received after the timeout is discarded. Default value is 2000 ms. 0 means no timeout. | Yes |
| Expiration | The expiration time (in milliseconds) of the message before it becomes obsolete. If you do not specify an expiration time, the default value is 0 (never expires). | No |
| Priority | The priority level of the message. There are ten priority levels from 0 (lowest) to 9 (highest). If you do not specify a priority level, the default level is 4. | No |
| Use non-persistent delivery mode? | Whether to set DeliveryMode.NON_PERSISTENT. | Yes |
| Content | The content of the message. | No |
| JMS Properties | The JMS Properties are properties specific for the underlying messaging system. You can setup the name, the value and the class (type) of value. Default type is String. For example: for WebSphere 5.1 web services you will need to set the JMS Property targetService to test webservices through JMS. | No |
| Initial Context Factory | The Initial Context Factory is the factory to be used to look up the JMS Resources. | No |
| JNDI properties | The JNDI Properties are the specific properties for the underlying JNDI implementation. | No |
| Provider URL | The URL for the JMS provider. | No |


### JUnit Request

The current implementation supports standard JUnit convention and extensions. It also includes extensions like oneTimeSetUp and oneTimeTearDown. The sampler works like the Java Request with some differences. The current implementation of the sampler will try to create an instance using the string constructor first. If the test class does not declare a string constructor, the sampler will look for an empty constructor. Example below: By default, JMeter will provide some default values for the success/failure code and message. Users should define a set of unique success and failure codes and use...

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. |  |
| Search for JUnit4 annotations | Select this to search for JUnit4 tests (@Test annotations) | Yes |
| Package filter | Comma separated list of packages to show. Example, org.apache.jmeter,junit.framework. |  |
| Class name | Fully qualified name of the JUnit test class. | Yes |
| Constructor string | String pass to the string constructor. If a string is set, the sampler will use the string constructor instead of the empty constructor. |  |
| Test method | The method to test. | Yes |
| Success message | A descriptive message indicating what success means. |  |
| Success code | An unique code indicating the test was successful. |  |
| Failure message | A descriptive message indicating what failure means. |  |
| Failure code | An unique code indicating the test failed. |  |
| Error message | A description for errors. |  |
| Error code | Some code for errors. Does not need to be unique. |  |
| Do not call setUp and tearDown | Set the sampler not to call setUp and tearDown. By default, setUp and tearDown should be called. Not calling those methods could affect the test and make it inaccurate. This option should only be used with calling oneTimeSetUp and oneTimeTearDown. If the selected method is oneTimeSetUp or oneTimeTea... | Yes |
| Append assertion errors | Whether or not to append assertion errors to the response message. | Yes |
| Append runtime exceptions | Whether or not to append runtime exceptions to the response message. Only applies if "Append assertion errors" is not selected. | Yes |
| Create a new Instance per sample | Whether or not to create a new JUnit instance for each sample. Defaults to false, meaning JUnit TestCase is created one and reused. | Yes |


### Mail Reader Sampler

The Mail Reader Sampler can read (and optionally delete) mail messages using POP3(S) or IMAP(S) protocols.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. |  |
| Server Type | The protocol used by the provider: e.g. pop3, pop3s, imap, imaps. or another string representing the server protocol. For example file for use with the read-only mail file provider. The actual provider names for POP3 and IMAP are pop3 and imap | Yes |
| Server | Hostname or IP address of the server. See below for use with file protocol. | Yes |
| Port | Port to be used to connect to the server (optional) | No |
| Username | User login name |  |
| Password | User login password (N.B. this stored unencrypted in the test plan) |  |
| Folder | The IMAP(S) folder to use. See below for use with file protocol. | Yes, if using IMAP(S) |
| Number of messages to retrieve | Set this to retrieve all or some messages | Yes |
| Fetch headers only | If selected, only the message headers will be retrieved. | Yes |
| Delete messages from the server | If set, messages will be deleted after retrieval | Yes |
| Store the message using MIME | Whether to store the message as MIME. If so, then the entire raw message is stored in the Response Data; the headers are not stored as they are available in the data. If not, the message headers are stored as Response Headers. A few headers are stored (Date, To, From, Subject) in the body. | Yes |
| Use no security features | Indicates that the connection to the server does not use any security protocol. |  |
| Use SSL | Indicates that the connection to the server must use the SSL protocol. |  |
| Use StartTLS | Indicates that the connection to the server should attempt to start the TLS protocol. |  |
| Enforce StartTLS | If the server does not start the TLS protocol the connection will be terminated. |  |
| Trust All Certificates | When selected it will accept all certificates independent of the CA. |  |
| Use local trustore | When selected it will only accept certificates that are locally trusted. |  |
| Local trustore | Path to file containg the trusted certificates. Relative paths are resolved against the current directory. Failing that, against the directory containg the test script (JMX file). |  |


### Flow Control Action(was: Test Action)

This sampler can also be useful in conjunction with the Transaction Controller, as it allows pauses to be included without needing to generate a sample. For variable delays, set the pause time to zero, and add a Timer as a child.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. |  |
| Target | Current Thread / All Threads (ignored for Pause and Go to next loop iteration) | Yes |
| Action | Pause / Stop / Stop Now / Go to next loop iteration | Yes |
| Duration | How long to pause for (milliseconds) | Yes, if Pause is selected |


### SMTP Sampler

The SMTP Sampler can send mail messages using SMTP/SMTPS protocol. It is possible to set security protocols for the connection (SSL and TLS), as well as user authentication. If a security protocol is used a verification the server certificate will occur. Two alternatives to handle this verification are available:

| Property | Description | Required |
|----------|-------------|----------|
| Server | Hostname or IP address of the server. See below for use with file protocol. | Yes |
| Port | Port to be used to connect to the server. Defaults are: SMTP=25, SSL=465, StartTLS=587 | No |
| Connection timeout | Connection timeout value in milliseconds (socket level). Default is infinite timeout. | No |
| Read timeout | Read timeout value in milliseconds (socket level). Default is infinite timeout. | No |
| Address From | The from address that will appear in the e-mail | Yes |
| Address To | The destination e-mail address (multiple values separated by ";") | Yes, unless CC or BCC is specified |
| Address To CC | Carbon copy destinations e-mail address (multiple values separated by ";") | No |
| Address To BCC | Blind carbon copy destinations e-mail address (multiple values separated by ";") | No |
| Address Reply-To | Alternate Reply-To address (multiple values separated by ";") | No |
| Use Auth | Indicates if the SMTP server requires user authentication |  |
| Username | User login name |  |
| Password | User login password (N.B. this stored unencrypted in the test plan) |  |
| Use no security features | Indicates that the connection to the SMTP server does not use any security protocol. |  |
| Use SSL | Indicates that the connection to the SMTP server must use the SSL protocol. |  |
| Use StartTLS | Indicates that the connection to the SMTP server should attempt to start the TLS protocol. |  |
| Enforce StartTLS | If the server does not start the TLS protocol the connection will be terminated. |  |
| Trust All Certificates | When selected it will accept all certificates independent of the CA. |  |
| Use local trustore | When selected it will only accept certificates that are locally trusted. |  |
| Local trustore | Path to file containg the trusted certificates. Relative paths are resolved against the current directory. Failing that, against the directory containg the test script (JMX file). |  |
| Override System SSL/TLS Protocols | Specify a custom SSL/TLS protocol as space separated list to use on handshake example TLSv1 TLSv1.1 TLSv1.2. Defaults to all supported protocols. | No |
| Subject | The e-mail message subject. |  |
| Suppress Subject Header | If selected, the "Subject:" header is omitted from the mail that is sent. This different from sending an empty "Subject:" header, though some e-mail clients may display it identically. |  |
| Include timestamp in subject | Includes the System.currentTimemillis() in the subject line. |  |
| Add Header | Additional headers can be defined using this button. | No |
| Message | The message body. |  |
| Send plain body (i.e. not multipart/mixed) | If selected, then send the body as a plain message, i.e. not multipart/mixed, if possible. If the message body is empty and there is a single file, then send the file contents as the message body. Note: If the message body is not empty, and there is at least one attached file, then the body is sent ... | No |
| Attach files | Files to be attached to the message. |  |
| Send .eml | If set, the .eml file will be sent instead of the entries in the Subject, Message, and Attach file(s) fields |  |
| Calculate message size | Calculates the message size and stores it in the sample result. |  |
| Enable debug logging? | If set, then the "mail.debug" property is set to "true" |  |


### OS Process Sampler

The OS Process Sampler is a sampler that can be used to execute commands on the local machine. It should allow execution of any command that can be run from the command line. Validation of the return code can be enabled, and the expected return code can be specified.

| Property | Description | Required |
|----------|-------------|----------|
| Command | The program name to execute. | Yes |
| Working directory | Directory from which command will be executed, defaults to folder referenced by "user.dir" System property | No |
| Command Parameters | Parameters passed to the program name. | No |
| Environment Parameters | Key/Value pairs added to environment when running command. | No |
| Standard input (stdin) | Name of file from which input is to be taken (STDIN). | No |
| Standard output (stdout | Name of output file for standard output (STDOUT). If omitted, output is captured and returned as the response data. | No |
| Standard error (stderr) | Name of output file for standard error (STDERR). If omitted, output is captured and returned as the response data. | No |
| Check Return Code | If checked, sampler will compare return code with Expected Return Code. | No |
| Expected Return Code | Expected return code for System Call, required if "Check Return Code" is checked. Note 500 is used as an error indicator in JMeter so you should not use it. | No |
| Timeout | Timeout for command in milliseconds, defaults to 0, which means *no*no timeout. If the timeout expires before the command finishes, JMeter will attempt to kill the OS process. | No |


### MongoDB Script (DEPRECATED)

This sampler lets you send a Request to a MongoDB.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this sampler that is shown in the tree. | No |
| MongoDB Source | Name of the JMeter variable that the MongoDB connection is bound to. This must agree with the 'MongoDB Source' field of a MongoDB Source Config. | Yes |
| Database Name | Database Name, will be used in your script | Yes |
| Username |  | No |
| Password |  | No |
| Script | Mongo script as it would be used in MongoDB shell | Yes |


### Bolt Request

This sampler allows you to run Cypher queries through the Bolt protocol.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this sampler that is shown in the tree. | No |
| Comments | Free text for additional details. | No |
| Cypher statement | The query to execute. | Yes |
| Params | The parameter values, JSON formatted. | No |
| Record Query Results | Whether to add or not query result data to the sampler response (default false). Note that activating this has a memory overhead, use it wisely. | No |
| Access Mode | Whether to access the database in WRITE or READ mode. Use WRITE for a standalone Neo4j instance. For a Neo4j cluster, select mode depending on whether the query writes to the database. That setting will allow correct routing to the cluster leader, followers or read replicas. | Yes |
| Database | The database to run the query against. Required for Neo4j 4.0+, unless querying the default database. Must be undefined for Neo4j 3.5. | No |
| Transaction timeout | Timeout for the transaction. | No |


## 18.2 Logic Controllers

### Simple Controller

The Simple Logic Controller lets you organize your Samplers and other Logic Controllers. Unlike other Logic Controllers, this controller provides no functionality beyond that of a storage device.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this controller that is shown in the tree. | No |


### Loop Controller

If you add Generative or Logic Controllers to a Loop Controller, JMeter will loop through them a certain number of times, in addition to the loop value you specified for the Thread Group. For example, if you add one HTTP Request to a Loop Controller with a loop count of two, and configure the Thread Group loop count to three, JMeter will send a total of 2 * 3 = 6 HTTP Requests.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this controller that is shown in the tree. | No |
| Loop Count | The number of times the subelements of this controller will be iterated each time through a test run. The value -1 is equivalent to checking the Forever toggle. **Special Case:**Special Case: The Loop Controller embedded in the Thread Group element behaves slightly different. Unless set ... | Yes, unless "Forever" is checked |


### Once Only Controller

The Once Only Logic Controller tells JMeter to process the controller(s) inside it only once per Thread, and pass over any requests under it during further iterations through the test plan.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this controller that is shown in the tree. | No |


### Interleave Controller

If you add Generative or Logic Controllers to an Interleave Controller, JMeter will alternate among each of the other controllers for each loop iteration.

| Property | Description | Required |
|----------|-------------|----------|
| name | Descriptive name for this controller that is shown in the tree. | No |
| ignore sub-controller blocks | If checked, the interleave controller will treat sub-controllers like single request elements and only allow one request per controller at a time. | No |
| Interleave across threads | If checked, the interleave controller will alternate among each of its children controllers for each loop iteration but across all threads, for example in a configuration with 4 threads and 3 child controllers, on first iteration thread 1 will run first child, thread 2 second child, thread 3 third c... | No |


### Random Controller

The Random Logic Controller acts similarly to the Interleave Controller, except that instead of going in order through its sub-controllers and samplers, it picks one at random at each pass.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this controller that is shown in the tree. | No |
| ignore sub-controller blocks | If checked, the interleave controller will treat sub-controllers like single request elements and only allow one request per controller at a time. | No |


### Random Order Controller

The Random Order Controller is much like a Simple Controller in that it will execute each child element at most once, but the order of execution of the nodes will be random.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this controller that is shown in the tree. | No |


### Throughput Controller

The Throughput Controller allows the user to control how often it is executed. There are two modes:

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this controller that is shown in the tree. | No |
| Execution Style | Whether the controller will run in percent executions or total executions mode. | Yes |
| Throughput | A number. For percent execution mode, a number from 0-100 that indicates the percentage of times the controller will execute. "50" means the controller will execute during half the iterations through the test plan. For total execution mode, the number indicates the total number of times the controll... | Yes |
| Per User | If checked, per user will cause the controller to calculate whether it should execute on a per user (per thread) basis. If unchecked, then the calculation will be global for all users. For example, if using total execution mode, and uncheck "per user", then the number given for throughput will be th... | No |


### Runtime Controller

The Runtime Controller controls how long its children will run. Controller will run its children until configured Runtime(s) is exceed.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this controller that is shown in the tree, and used to name the transaction. | Yes |
| Runtime (seconds) | Desired runtime in seconds. 0 means no run. | Yes |


### If Controller

The If Controller allows the user to control whether the test elements below it (its children) are run or not.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this controller that is shown in the tree. | No |
| Condition (default JavaScript) | By default the condition is interpreted as **JavaScript**JavaScript code that returns "true" or "false", but this can be overridden (see below) | Yes |
| Interpret Condition as Variable Expression? | If this selected, then the condition must be an expression that evaluates to "true" (case is ignored). For example, ${FOUND} or ${__jexl3(${VAR} > 100)}. Unlike the JavaScript case, the condition is only checked to see if it matches "true" (case is ignored). Checking this and using __jexl3__jexl3... | Yes |
| Evaluate for all children | Should condition be evaluated for all children? If not checked, then the condition is only evaluated on entry. | Yes |


### While Controller

The While Controller runs its children until the condition is "false".

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this controller that is shown in the tree, and used to name the transaction. | No |
| Condition | blank, LAST, or variable/function | No |


### Switch Controller

The Switch Controller acts like the Interleave Controller in that it runs one of the subordinate elements on each iteration, but rather than run them in sequence, the controller runs the element defined by the switch value.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this controller that is shown in the tree. | No |
| Switch Value | The number (or name) of the subordinate element to be invoked. Elements are numbered from 0. Defaults to 0 | No |


### ForEach Controller

A ForEach controller loops through the values of a set of related variables. When you add samplers (or controllers) to a ForEach controller, every sample (or controller) is executed one or more times, where during every loop the variable has a new value. The input should consist of several variables, each extended with an underscore and a number. Each such variable must have a value. So for example when the input variable has the name inputVar, the following variables should have been defined:

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this controller that is shown in the tree. | No |
| Input variable prefix | Prefix for the variable names to be used as input. Defaults to an empty string as prefix. | No |
| Start index for loop | Start index (exclusive) for loop over variables (first element is at start index + 1) | No |
| End index for loop | End index (inclusive) for loop over variables | No |
| Output variable | The name of the variable which can be used in the loop for replacement in the samplers. Defaults to an empty variable name, which is most probably not wanted. | No |
| Use Separator | If not checked, the "_" separator is omitted. | Yes |


### Module Controller

The Module Controller provides a mechanism for substituting test plan fragments into the current test plan at run-time.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this controller that is shown in the tree. | No |
| Module to Run | The module controller provides a list of all controllers loaded into the gui. Select the one you want to substitute in at runtime. | Yes |


### Include Controller

The include controller is designed to use an external JMX file. To use it, create a Test Fragment underneath the Test Plan and add any desired samplers, controllers etc. below it. Then save the Test Plan. The file is now ready to be included as part of other Test Plans.

| Property | Description | Required |
|----------|-------------|----------|
| Filename | The file to include. | Yes |


### Transaction Controller

The Transaction Controller generates an additional sample which measures the overall time taken to perform the nested test elements.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this controller that is shown in the tree, and used to name the transaction. | Yes |
| Generate Parent Sample | If checked, then the sample is generated as a parent of the other samples, otherwise the sample is generated as an independent sample. | Yes |
| Include duration of timer and pre-post processors in generated sample | Whether to include timer, pre- and post-processing delays in the generated sample. Default is false | Yes |


### Recording Controller

The Recording Controller is a place holder indicating where the proxy server should record samples to. During test run, it has no effect, similar to the Simple Controller. But during recording using the HTTP(S) Test Script Recorder, all recorded samples will by default be saved under the Recording Controller.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this controller that is shown in the tree. | No |


### Critical Section Controller

The Critical Section Controller ensures that its children elements (samplers/controllers, etc.) will be executed by only one thread as a named lock will be taken before executing children of controller.

| Property | Description | Required |
|----------|-------------|----------|
| Lock Name | Lock that will be taken by controller, ensure you use different lock names for unrelated sections | Yes |


## 18.3 Listeners

### Sample Result Save Configuration

Listeners can be configured to save different items to the result log files (JTL) by using the Config popup as shown below. The defaults are defined as described in the Listener Default Configuration documentation. Items with (CSV) after the name only apply to the CSV format; items with (XML) only apply to XML format. CSV format cannot currently be used to save any items that include line-breaks.


### Graph Results

The Graph Results listener generates a simple graph that plots all sample times. Along the bottom of the graph, the current sample (black), the current average of all samples (blue), the current standard deviation (red), and the current throughput rate (green) are displayed in milliseconds.


### Assertion Results

The Assertion Results visualizer shows the Label of each sample taken. It also reports failures of any Assertions that are part of the test plan.


### View Results Tree

There are several ways to view the response, selectable by a drop-down box at the bottom of the left hand panel.


### Aggregate Report

The throughput is calculated from the point of view of the sampler target (e.g. the remote server in the case of HTTP samples). JMeter takes into account the total time over which the requests have been generated. If other samplers and timers are in the same thread, these will increase the total time, and therefore reduce throughput value. So two identical samplers with different names will have half the throughput of two samplers with the same name. It is important to choose the sampler names correctly to get the best results from the Aggregate Report.


### View Results in Table

By default, it only displays the main (parent) samples; it does not display the sub-samples (child samples). JMeter has a "Child Samples?" check-box. If this selected, then the sub-samples are displayed instead of the main samples.


### Simple Data Writer

This listener can record results to a file but not to the UI. It is meant to provide an efficient means of recording data by eliminating GUI overhead. When running in CLI mode, the -l flag can be used to create a data file. The fields to save are defined by JMeter properties. See the jmeter.properties file for details.


### Aggregate Graph

The aggregate graph is similar to the aggregate report. The primary difference is the aggregate graph provides an easy way to generate bar graphs and save the graph as a PNG file.

| Property | Description | Required |
|----------|-------------|----------|
| Column settings | Columns to display: Choose the column(s) to display in graph. Rectangles color: Click on right color rectangle open a popup dialog to choose a custom color for column. Foreground color Allow to change the value text color. Value font: Allow to define font settings for the text. Draw outlines bar? To... | Yes |
| Title | Define the graph's title on the head of chart. Empty value is the default value: "Aggregate Graph". The button Synchronize with name define the title with the label of the listener. And define font settings for graph title | No |
| Graph size | Compute the graph size by the width and height depending of the current JMeter's window size. Use Width and Height fields to define a custom size. The unit is pixel. | No |
| X Axis settings | Define the max length of X Axis label (in pixel). | No |
| Y Axis settings | Define a custom maximum value for Y Axis. | No |
| Legend | Define the placement and font settings for chart legend | Yes |


### Response Time Graph

The Response Time Graph draws a line chart showing the evolution of response time during the test, for each labelled request. If many samples exist for the same timestamp, the mean value is displayed.

| Property | Description | Required |
|----------|-------------|----------|
| Interval (ms) | The time in milliseconds for X axis interval. Samples are grouped according to this value. Before display the graph, click on Apply interval button to refresh internal data. | Yes |
| Sampler label selection | Filter by result label. A regular expression can be used, ex. .*Transaction.*. Before display the graph, click on Apply filter button to refresh internal data. | No |
| Title | Define the graph's title on the head of chart. Empty value is the default value: "Response Time Graph". The button Synchronize with name define the title with the label of the listener. And define font settings for graph title | No |
| Line settings | Define the width of the line. Define the type of each value point. Choose none to have a line without mark | Yes |
| Graph size | Compute the graph size by the width and height depending of the current JMeter's window size. Use Width and Height fields to define a custom size. The unit is pixel. | No |
| X Axis settings | Customize the date format of X axis label. The syntax is the Java SimpleDateFormat API. | No |
| Y Axis settings | Define a custom maximum value for Y Axis in milli-seconds. Define the increment for the scale (in ms) Show or not the number grouping in Y Axis labels. | No |
| Legend | Define the placement and font settings for chart legend | Yes |


### Mailer Visualizer

The mailer visualizer can be set up to send email if a test run receives too many failed responses from the server.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. | No |
| From | Email address to send messages from. | Yes |
| Addressee(s) | Email address to send messages to, comma-separated. | Yes |
| Success Subject | Email subject line for success messages. | No |
| Success Limit | Once this number of successful responses is exceed **after previously reaching the failure limit**after previously reaching the failure limit, a success email is sent. The mailer will thus only send out messages in a sequence of failed-succeed-failed-succeed, etc. | Yes |
| Failure Subject | Email subject line for fail messages. | No |
| Failure Limit | Once this number of failed responses is exceed, a failure email is sent - i.e. set the count to 0 to send an e-mail on the first failure. | Yes |
| Host | IP address or host name of SMTP server (email redirector) server. | No |
| Port | Port of SMTP server (defaults to 25). | No |
| Login | Login used to authenticate. | No |
| Password | Password used to authenticate. | No |
| Connection security | Type of encryption for SMTP authentication (SSL, TLS or none). | No |
| Test Mail | Press this button to send a test mail | No |
| Failures | A field that keeps a running total of number of failures so far received. | No |


### BeanShell Listener

The BeanShell Listener allows the use of BeanShell for processing samples for saving etc.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. The name is stored in the script variable Label |  |
| Reset bsh.Interpreter before each call | If this option is selected, then the interpreter will be recreated for each sample. This may be necessary for some long running scripts. For further information, see Best Practices - BeanShell scripting. | Yes |
| Parameters | Parameters to pass to the BeanShell script. The parameters are stored in the following variables: Parameters string containg the parameters a single variable bsh.args String array containg parameters, split on white-space | No |
| Script file | A file containg the BeanShell script to run. The file name is stored in the script variable FileName | No |
| Script | The BeanShell script to run. The return value is ignored. | Yes (unless script file is provided) |


### Summary Report

The throughput is calculated from the point of view of the sampler target (e.g. the remote server in the case of HTTP samples). JMeter takes into account the total time over which the requests have been generated. If other samplers and timers are in the same thread, these will increase the total time, and therefore reduce throughput value. So two identical samplers with different names will have half the throughput of two samplers with the same name. It is important to choose the sampler labels correctly to get the best results from the Report.


### Save Responses to a file

This test element can be placed anywhere in the test plan. For each sample in its scope, it will create a file of the response Data. The primary use for this in creating functional tests, but it can also be useful where the response is too large to be displayed in the View Results Tree Listener. The file name is created from the specified prefix, plus a number (unless this disabled, see below). The file extension is created from the document type, if known. If not known, the file extension is set to 'unknown'. If numbering is disabled, and adding a suffix is disabled, th...

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. | No |
| Filename Prefix (can include folders) | Prefix for the generated file names; this can include a directory name. Relative paths are resolved relative to the current working directory (which defaults to the bin/ directory). JMeter also supports paths relative to the directory containg the current test plan (JMX file). If the path name beg... | Yes |
| Variable Name containg saved file name | Name of a variable in which to save the generated file name (so it can be used later in the test plan). If there are sub-samples then a numeric suffix is added to the variable name. E.g. if the variable name is FILENAME, then the parent sample file name is saved in the variable FILENAME, and the fil... | No |
| Minimum Length of sequence number | If "Don't add number to prefix" is not checked, then numbers added to prefix will be padded by 0 so that prefix is has size of this value. Defaults to 0. | No |
| Save Failed Responses only | If selected, then only failed responses are saved | Yes |
| Save Successful Responses only | If selected, then only successful responses are saved | Yes |
| Don't add number to prefix | If selected, then no number is added to the prefix. If you select this option, make sure that the prefix is unique or the file may be overwritten. | Yes |
| Don't add content type suffix | If selected, then no suffix is added. If you select this option, make sure that the prefix is unique or the file may be overwritten. | Yes |
| Add timestamp | If selected, then date will be included in file suffix following format yyMMdd-HHmm_ | Yes |
| Don't Save Transaction Controller SampleResult | If selected, then SamplerResult generated by Transaction Controller will be ignored | Yes |


### JSR223 Listener

The JSR223 Listener allows JSR223 script code to be applied to sample results.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. | No |
| Language | The JSR223 language to be used | Yes |
| Parameters | Parameters to pass to the script. The parameters are stored in the following variables: Parameters string containg the parameters a single variable args String array containg parameters, split on white-space | No |
| Script file | A file containg the script to run, if a relative file path is used, then it will be relative to directory referenced by "user.dir" System property | No |
| Script compilation caching | Unique String across Test Plan that JMeter will use to cache result of Script compilation if language used supports Compilable interface (Groovy is one of these, java, beanshell and javascript are not). See note in JSR223 Sampler Java System property if you're using Groovy without checking... | No |
| Script | The script to run. | Yes (unless script file is provided) |


### Generate Summary Results

The label is used to group sample results together. So if you have multiple Thread Groups and want to summarize across them all, then use the same label - or add the summariser to the Test Plan (so all thread groups are in scope). Different summary groupings can be implemented by using suitable labels and adding the summarisers to appropriate parts of the test plan.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. It appears as the "label" in the output. Details for all elements with the same label will be added together. | Yes |


### Comparison Assertion Visualizer

The Comparison Assertion Visualizer shows the results of any Compare Assertion elements.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. | Yes |


### Backend Listener

The backend listener is an Asynchronous listener that enables you to plug custom implementations of BackendListenerClient. By default, a Graphite implementation is provided.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. | Yes |
| Backend Listener implementation | Class of the BackendListenerClient implementation. | Yes |
| Async Que size | Size of the que that holds the SampleResults while they are processed asynchronously. | Yes |
| Parameters | Parameters of the BackendListenerClient implementation. | Yes |


## 18.4 Configuration Elements

### CSV Data Set Config

CSV Data Set Config is used to read lines from a file, and split them into variables. It is easier to use than the __CSVRead()__CSVRead() and __StringFromFile()__StringFromFile() functions. It is well suited to handling large numbers of variables, and is also useful for testing with "random" and unique values.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. |  |
| Filename | Name of the file to be read. **Relative file names are resolved with respect to the path of the active test plan.**Relative file names are resolved with respect to the path of the active test plan. **For distributed testing, the CSV file must be stored on the server host system in the correct relati... | Yes |
| File Encoding | The encoding to be used to read the file, if not the platform default. | No |
| Variable Names | List of variable names. The names must be separated by the delimiter character. They can be quoted using double-quotes. JMeter supports CSV header lines: if the variable name field empty, then the first line of the file is read and interpreted as the list of column names. | No |
| Use first line as Variable Names | Ignore first line of CSV file, it will only be used if Variable Names is not empty, if Variable Names is empty the first line must contain the headers. | No |
| Delimiter | Delimiter to be used to split the records in the file. If there are fewer values on the line than there are variables the remaing variables are not updated - so they will retain their previous value (if any). | Yes |
| Allow quoted data? | Should the CSV file allow values to be quoted? If enabled, then values can be enclosed in " - double-quote - allowing values to contain a delimiter. | Yes |
| Recycle on EOF? | Should the file be re-read from the beginning on reaching EOF? (default is true) | Yes |
| Stop thread on EOF? | Should the thread be stopped on EOF, if Recycle is false? (default is false) | Yes |
| Sharing mode | All threads - (the default) the file is shared between all the threads. Current thread group - each file is opened once for each thread group in which the element appears Current thread - each file is opened separately for each thread Identifier - all threads sharing the same identifier share the sa... | Yes |


### FTP Request Defaults


### DNS Cache Manager

The DNS Cache Manager element allows to test applications, which have several servers behind load balancers (CDN, etc.), when user receives content from different IP's. By default JMeter uses JVM DNS cache. That's why only one server from the cluster receives load. DNS Cache Manager resolves names for each thread separately each iteration and saves results of resolving to its internal DNS Cache, which is independent from both JVM and OS DNS caches.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. | No |
| Clear cache each Iteration | If selected, DNS cache of every Thread is cleared each time new iteration is started. | No |
| Use system DNS resolver | System DNS resolver will be used. For correct work edit $JAVA_HOME/jre/lib/security/java.security and add networkaddress.cache.ttl=0 | N/A |
| Use custom DNS resolver | Custom DNS resolver (from dnsjava library) will be used. | N/A |
| Hostname or IP address | List of DNS servers to use. If empty, network configuration DNS will used. | No |
| Add Button | Add an entry to the DNS servers table. | N/A |
| Delete Button | Delete the currently selected table entry. | N/A |
| Host and Hostname or IP address | Mapping of hostnames to a static host entry which will be resolved using the custom DNS resolver. | No |
| Add static host Button | Add an entry to the static hosts table. | N/A |
| Delete static host Button | Delete the currently selected static host in the table. | N/A |


### HTTP Authorization Manager

The Authorization Manager lets you specify one or more user logins for web pages that are restricted using server authentication. You see this type of authentication when you use your browser to access a restricted page, and your browser displays a login dialog box. JMeter transmits the login information when it encounters this type of page.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. | No |
| Clear auth on each iteration? | Used by Kerberos authentication. If checked, authentication will be done on each iteration of Main Thread Group loop even if it has already been done in a previous one. This usually useful if each main thread group iteration represents behaviour of one Virtual User. | Yes |
| Base URL | A partial or complete URL that matches one or more HTTP Request URLs. As an example, say you specify a Base URL of "http://localhost/restricted/" with a Username of "jmeter" and a Password of "jmeter". If you send an HTTP request to the URL "http://localhost/restricted/ant/myPage.html", the Authoriz... | Yes |
| Username | The username to authorize. | Yes |
| Password | The password for the user. (N.B. this stored unencrypted in the test plan) | Yes |
| Domain | The domain to use for NTLM. | No |
| Realm | The realm to use for NTLM. | No |
| Mechanism | Type of authentication to perform. JMeter can perform different types of authentications based on used Http Samplers: Java BASIC HttpClient 4 BASIC, DIGEST and Kerberos | No |


### HTTP Cache Manager

The HTTP Cache Manager is used to add caching functionality to HTTP requests within its scope to simulate browser cache feature. Each Virtual User thread has its own Cache. By default, Cache Manager will store up to 5000 items in cache per Virtual User thread, using LRU algorithm. Use property "maxSize" to modify this value. Note that the more you increase this value the more HTTP Cache Manager will consume memory, so be sure to adapt the -Xmx JVM option accordingly.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. | No |
| Clear cache each iteration | If selected, then the cache is cleared at the start of the thread. | Yes |
| Use Cache Control/Expires header when processing GET requests | See description above. | Yes |
| Max Number of elements in cache | See description above. | Yes |


### HTTP Cookie Manager

The Cookie Manager element has two functions: First, it stores and sends cookies just like a web browser. If you have an HTTP Request and the response contains a cookie, the Cookie Manager automatically stores that cookie and will use it for all future requests to that particular web site. Each JMeter thread has its own "cookie storage area". So, if you are testing a web site that uses a cookie for storing session information, each JMeter thread will have its own session. Note that such cookies do not appear on the Cookie Manager display, but they can be seen using the View Results TreeView Re...

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. | No |
| Clear Cookies each Iteration | If selected, all server-defined cookies are cleared each time the main Thread Group loop is executed. Any cookie defined in the GUI are not cleared. | Yes |
| Cookie Policy | The cookie policy that will be used to manage the cookies. "standard" is the default since 3.0, and should work in most cases. See Cookie specifications and CookieSpec implementations [Note: "ignoreCookies" is equivalent to omitting the CookieManager.] | Yes |
| Implementation | HC4CookieHandler (HttpClient 4.5.X API). Default is HC4CookieHandler since 3.0. *[Note: If you have a website to test with IPv6 address, choose HC4CookieHandler (IPv6 compliant)]*[Note: If you have a website to test with IPv6 address, choose HC4CookieHandler (IPv6 compliant)] | Yes |
| User-Defined Cookies | This gives you the opportunity to use hardcoded cookies that will be used by all threads during the test execution. The "domain" is the hostname of the server (without http://); the port is currently ignored. | No (discouraged, unless you know what you're doing) |
| Add Button | Add an entry to the cookie table. | N/A |
| Delete Button | Delete the currently selected table entry. | N/A |
| Load Button | Load a previously saved cookie table and add the entries to the existing cookie table entries. | N/A |
| Save As Button | Save the current cookie table to a file (does not save any cookies extracted from HTTP Responses). | N/A |


### HTTP Request Defaults

This element lets you set default values that your HTTP Request controllers use. For example, if you are creating a Test Plan with 25 HTTP Request controllers and all of the requests are being sent to the same server, you could add a single HTTP Request Defaults element with the "Server Name or IP" field filled in. Then, when you add the 25 HTTP Request controllers, leave the "Server Name or IP" field empty. The controllers will inherit this field value from the HTTP Request Defaults element.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. | No |
| Server | Domain name or IP address of the web server. E.g. www.example.com. [Do not include the http:// prefix. | No |
| Port | Port the web server is listening to. | No |
| Connect Timeout | Connection Timeout. Number of milliseconds to wait for a connection to open. | No |
| Response Timeout | Response Timeout. Number of milliseconds to wait for a response. | No |
| Implementation | Java, HttpClient4. If not specified the default depends on the value of the JMeter property jmeter.httpsampler, failing that, the Java implementation is used. | No |
| Protocol | HTTP or HTTPS. | No |
| Content encoding | The encoding to be used for the request. | No |
| Path | The path to resource (for example, /servlets/myServlet). If the resource requires query string parameters, add them below in the "Send Parameters With the Request" section. Note that the path is the default for the full path, not a prefix to be applied to paths specified on the HTTP Request screens. | No |
| Send Parameters With the Request | The query string will be generated from the list of parameters you provide. Each parameter has a *name*name and *value*value. The query string will be generated in the correct fashion, depending on the choice of "Method" you made (i.e. if you chose GET, the query string will be appended to the URL, ... | No |
| Server (proxy) | Hostname or IP address of a proxy server to perform request. [Do not include the http:// prefix.] | No |
| Port | Port the proxy server is listening to. | No, unless proxy hostname is specified |
| Username | (Optional) username for proxy server. | No |
| Password | (Optional) password for proxy server. (N.B. this stored unencrypted in the test plan) | No |
| Retrieve All Embedded Resources from HTML Files | Tell JMeter to parse the HTML file and send HTTP/HTTPS requests for all images, Java applets, JavaScript files, CSSs, etc. referenced in the file. | No |
| Use concurrent pool | Use a pool of concurrent connections to get embedded resources. | No |
| Size | Pool size for concurrent connections used to get embedded resources. | No |
| URLs must match: | If present, this must be a regular expression that is used to match against any embedded URLs found. So if you only want to download embedded resources from http://example.invalid/, use the expression: http://example\.invalid/.* | No |
| URLs must not match: | If present, this must be a regular expression that is used to filter out any embedded URLs found. So if you don't want to download PNG or SVG files from any source, use the expression: .*\.(?i:svg\|png) | No |


### HTTP Header Manager

The Header Manager lets you add or override HTTP request headers.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. | No |
| Name (Header) | Name of the request header. Two common request headers you may want to experiment with are "User-Agent" and "Refer". | No (You should have at least one, however) |
| Value | Request header value. | No (You should have at least one, however) |
| Add Button | Add an entry to the header table. | N/A |
| Delete Button | Delete the currently selected table entry. | N/A |
| Load Button | Load a previously saved header table and add the entries to the existing header table entries. | N/A |
| Save As Button | Save the current header table to a file. | N/A |


### Java Request Defaults

The Java Request Defaults component lets you set default values for Java testing. See the Java Request.


### JDBC Connection Configuration

Creates a database connection (used by JDBC RequestSampler) from the supplied JDBC Connection settings. The connection may be optionally pooled between threads. Otherwise each thread gets its own connection. The connection configuration name is used by the JDBC Sampler to select the appropriate connection. The used pool is DBCP, see BasicDataSource Configuration Parameters

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for the connection configuration that is shown in the tree. | No |
| Variable Name for created pool | The name of the variable the connection is tied to. Multiple connections can be used, each tied to a different variable, allowing JDBC Samplers to select the appropriate connection. Each name must be different. If there are two configuration elements using the same name, only one will be saved. JMet... | Yes |
| Max Number of Connections | Maximum number of connections allowed in the pool. In most cases, **set this to zero (0)**set this to zero (0). This means that each thread will get its own pool with a single connection it, i.e. the connections are not shared between threads. If you really want to use shared pooling (why?), then... | Yes |
| Max Wait (ms) | Pool throws an error if the timeout period is exceed in the process of trying to retrieve a connection, see BasicDataSource.html#getMaxWaitMillisBasicDataSource.html#getMaxWaitMillis | Yes |
| Time Between Eviction Runs (ms) | The number of milliseconds to sleep between runs of the idle object evictor thread. When non-positive, no idle object evictor thread will be run. (Defaults to "60000", 1 minute). See BasicDataSource.html#getTimeBetweenEvictionRunsMillisBasicDataSource.html#getTimeBetweenEvictionRunsMillis | Yes |
| Auto Commit | Turn auto commit on or off for the connections. | Yes |
| Transaction isolation | Transaction isolation level | Yes |
| Pool Prepared Statements | Max number of Prepared Statements to pool per connection. "-1" disables the pooling and "0" means unlimited number of Prepared Statements to pool. (Defaults to "-1") | Yes |
| Preinit Pool | The connection pool can be initialized instantly. If set to False (default), the JDBC request samplers using this pool might measure higher response times for the first queries – as the connection establishment time for the whole pool is included. | No |
| Init SQL statements separated by new line | A Collection of SQL statements that will be used to initialize physical connections when they are first created. These statements are executed only once - when the configured connection factory creates the connection. | No |
| Test While Idle | Test idle connections of the pool, see BasicDataSource.html#getTestWhileIdleBasicDataSource.html#getTestWhileIdle. Validation Query will be used to test it. | Yes |
| Soft Min Evictable Idle Time(ms) | Minimum amount of time a connection may sit idle in the pool before it is eligible for eviction by the idle object evictor, with the extra condition that least minIdle connections remain the pool. See BasicDataSource.html#getSoftMinEvictableIdleTimeMillisBasicDataSource.html#getSoftMinEvictabl... | Yes |
| Validation Query | A simple query used to determine if the database is still responding. This defaults to the 'isValid()' method of the jdbc driver, which is suitable for many databases. However some may require a different query; for example Oracle something like 'SELECT 1 FROM DUAL' could be used. The list of the va... | No |
| Database URL | JDBC Connection string for the database. | Yes |
| JDBC Driver class | Fully qualified name of driver class. (Must be in JMeter's classpath - easiest to copy .jar file into JMeter's /lib directory). The list of the preconfigured jdbc driver classes can be configured with jdbc.config.jdbc.driver.class property and are by default: hsqldb org.hsqldb.jdbc.JDBCDriver Oracle... | Yes |
| Username | Name of user to connect as. | No |
| Password | Password to connect with. (N.B. this stored unencrypted in the test plan) | No |
| Connection Properties | Connection Properties to set when establishing connection (like internal_logon=sysdba for Oracle for example) | No |


### Keystore Configuration

The Keystore Config Element lets you configure how Keystore will be loaded and which keys it will use. This component is typically used in HTTPS scenarios where you don't want to take into account keystore initialization into account in response time.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. | No |
| Preload | Whether or not to preload Keystore. Setting it to true is usually the best option. | Yes |
| Variable name holding certificate alias | Variable name that will contain the alias to use for authentication by client certificate. Variable value will be filled from CSV Data Set for example. In the screenshot, "certificat_ssl" will also be a variable in CSV Data Set. Defaults to clientCertAliasVarName | False |
| Alias Start Index | The index of the first key to use in Keystore, 0-based. | Yes |
| Alias End Index | The index of the last key to use in Keystore, 0-based. When using "Variable name holding certificate alias" ensure it is large enough so that all keys are loaded at startup. Default to -1 which means load all. | Yes |


### Login Config Element

The Login Config Element lets you add or override username and password settings in samplers that use username and password as part of their setup.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. | No |
| Username | The default username to use. | No |
| Password | The default password to use. (N.B. this stored unencrypted in the test plan) | No |


### LDAP Request Defaults

The LDAP Request Defaults component lets you set default values for LDAP testing. See the LDAP Request.


### LDAP Extended Request Defaults

The LDAP Extended Request Defaults component lets you set default values for extended LDAP testing. See the LDAP Extended Request.


### TCP Sampler Config

The TCP Sampler Config provides default data for the TCP Sampler

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. |  |
| TCPClient classname | Name of the TCPClient class. Defaults to the property tcp.handler, failing that TCPClientImpl. | No |
| ServerName or IP | Name or IP of TCP server |  |
| Port Number | Port to be used |  |
| Re-use connection | If selected, the connection is kept open. Otherwise it is closed when the data has been read. | Yes |
| Close connection | If selected, the connection will be closed after running the sampler. | Yes |
| SO_LINGER | Enable/disable SO_LINGER with the specified linger time in seconds when a socket is created. If you set "SO_LINGER" value as 0, you may prevent large numbers of sockets sitting around with a TIME_WAIT status. | No |
| End of line(EOL) byte value | Byte value for end of line, set this to a value outside the range -128 to +127 to skip EOL checking. You may set this in jmeter.properties file as well with the tcp.eolByte property. If you set this in TCP Sampler Config and in jmeter.properties file at the same time, the setting value in the TCP Sa... | No |
| Connect Timeout | Connect Timeout (milliseconds, 0 disables). | No |
| Response Timeout | Response Timeout (milliseconds, 0 disables). | No |
| Set Nodelay | Should the nodelay property be set? |  |
| Text to Send | Text to be sent |  |


### User Defined Variables

The User Defined Variables element lets you define an **initial set of variables**initial set of variables, just as in the Test Plan.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. |  |
| User Defined Variables | Variable name/value pairs. The string under the "Name" column is what you'll need to place inside the brackets in ${…} constructs to use the variables later on. The whole ${…} will then be replaced by the string in the "Value" column. |  |


### Random Variable

The Random Variable Config Element is used to generate random numeric strings and store them in variable for use later. It's simpler than using User Defined Variables together with the __Random()__Random() function.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. | Yes |
| Variable Name | The name of the variable in which to store the random string. | Yes |
| Format String | The java.text.DecimalFormat format string to be used. For example "000" which will generate numbers with at least 3 digits, or "USER_000" which will generate output of the form USER_nnn. If not specified, the default is to generate the number using Long.toString() | No |
| Minimum Value | The minimum value (long) of the generated random number. | Yes |
| Maximum Value | The maximum value (long) of the generated random number. | Yes |
| Random Seed | The seed for the random number generator. If you use the same seed value with Per Thread set to true, you will get the same value for each Thread as per Random class. If no seed is set, Default constructor of Random will be used. | No |
| Per Thread(User)? | If False, the generator is shared between all threads in the thread group. If True, then each thread has its own random generator. | Yes |


### Counter

Allows the user to create a counter that can be referenced anywhere in the Thread Group. The counter config lets the user configure a starting point, a maximum, and the increment. The counter will loop from the start to the max, and then start over with the start, continuing on like that until the test is ended.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. |  |
| Starting value | The starting value for the counter. The counter will equal this value during the first iteration (defaults to 0). | No |
| Increment | How much to increment the counter by after each iteration (defaults to 0, meaning no increment). | Yes |
| Maximum value | If the counter exceeds the maximum, then it is reset to the Starting value. Default is Long.MAX_VALUE | No |
| Format | Optional format, e.g. 000 will format as 001, 002, etc. This passed to DecimalFormat, so any valid formats can be used. If there is a problem interpreting the format, then it is ignored. [The default format is generated using Long.toString()] | No |
| Exported Variable Name | This will be the variable name under which the counter value is available. If you name it counterA, you can then access it using ${counterA} as explained in user-defined values (By default, it creates an empty string variable that can be accessed using ${} but this highly disco... | No |
| Track Counter Independently for each User | In other words, is this a global counter, or does each user get their own counter? If unchecked, the counter is global (i.e., user #1 will get value "1", and user #2 will get value "2" on the first iteration). If checked, each user has an independent counter. | No |
| Reset counter on each Thread Group Iteration | This option is only available when counter is tracked per User, if checked, counter will be reset to Start value on each Thread Group iteration. This can be useful when Counter is inside a Loop Controller. | No |


### Simple Config Element

The Simple Config Element lets you add or override arbitrary values in samplers. You can choose the name of the value and the value itself. Although some adventurous users might find a use for this element, it's here primarily for developers a basic GUI that they can use while developing new JMeter components.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. | Yes |
| Parameter Name | The name of each parameter. These values are internal to JMeter's workings and are not generally documented. Only those familiar with the code will know these values. | Yes |
| Parameter Value | The value to apply to that parameter. | Yes |


### MongoDB Source Config (DEPRECATED)

You can then access com.mongodb.DB object in Beanshell or JSR223 Test Elements through the element MongoDBHolder using this code

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for the connection configuration that is shown in the tree. | No |
| Server Address List | Mongo DB Servers | Yes |
| MongoDB Source | The name of the variable the connection is tied to. Each name must be different. If there are two configuration elements using the same name, only one will be saved. | Yes |
| Keep Trying | If true, the driver will keep trying to connect to the same server in case that the socket cannot be established. There is maximum amount of time to keep retrying, which is 15s by default. This can be useful to avoid some exceptions being thrown when a server is down temporarily blocking the oper... | No |
| Maximum connections per host |  | No |
| Connection timeout | The connection timeout in milliseconds. It is used solely when establishing a new connection Socket.connect(java.net.SocketAddress, int) Default is 0 and means no timeout. | No |
| Maximum retry time | The maximum amount of time in milliseconds to spend retrying to open connection to the same server. Default is 0, which means to use the default 15s if autoConnectRetry is on. | No |
| Maximum wait time | The maximum wait time in milliseconds that a thread may wait for a connection to become available. Default is 120,000. | No |
| Socket timeout | The socket timeout in milliseconds It is used for I/O socket read and write operations Socket.setSoTimeout(int) Default is 0 and means no timeout. | No |
| Socket keep alive | This flag controls the socket keep alive feature that keeps a connection alive through firewalls Socket.setKeepAlive(boolean) Default is false. | No |
| ThreadsAllowedToBlockForConnectionMultiplier | This multiplier, multiplied with the connectionsPerHost setting, gives the maximum number of threads that may be waiting for a connection to become available from the pool. All further threads will get an exception right away. For example if connectionsPerHost is 10 and threadsAllowedToBlockForConne... | No |
| Write Concern: Safe | If true the driver will use a WriteConcern of WriteConcern.SAFE for all operations. If w, wtimeout, fsync or j are specified, this setting is ignored. Default is false. | No |
| Write Concern: Fsync | The fsync value of the global WriteConcern. Default is false. | No |
| Write Concern: Wait for Journal | The j value of the global WriteConcern. Default is false. | No |
| Write Concern: Wait for servers | The w value of the global WriteConcern. Default is 0. | No |
| Write Concern: Wait timeout | The wtimeout value of the global WriteConcern. Default is 0. | No |
| Write Concern: Continue on error | If batch inserts should continue after the first error | No |


### Bolt Connection Configuration

Creates a Bolt connection pool (used by Bolt Request Sampler) from the supplied Connection settings.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this sampler that is shown in the tree. | No |
| Comments | Free text for additional details. | No |
| Bolt URI | The database URI. | Yes |
| Username | User account. | No |
| Password | User credentials. | No |
| Connection Pool Max Size | Max size of the Neo4j driver Bolt connection pool. Raise the value if running large number of concurrent threads, so that JMeter threads are not blocked waiting for a connection to be released to the pool. | Yes |


## 18.5 Assertions

### Response Assertion

The response assertion control panel lets you add pattern strings to be compared against various fields of the request or response. The pattern strings are:

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. | No |
| Apply to: | This for use with samplers that can generate sub-samples, e.g. HTTP Sampler with embedded resources, Mail Reader or samples generated by the Transaction Controller. Main sample only - only applies to the main sample Sub-samples only - only applies to the sub-samples Main sample and sub-samples - ... | Yes |
| Field to Test | Instructs JMeter which field of the Request or Response to test. Text Response - the response text from the server, i.e. the body, excluding any HTTP headers. Request data - the request text sent to the server, i.e. the body, excluding any HTTP headers. Response Code - e.g. 200 Response Message - e.... | Yes |
| Ignore status | Instructs JMeter to set the status to success initially. The overall success of the sample is determined by combing the result of the assertion with the existing Response status. When the Ignore Status checkbox is selected, the Response status is forced to successful before evaluating the Assertio... | Yes |
| Pattern Matching Rules | Indicates how the text being tested is checked against the pattern. Contains - true if the text contains the regular expression pattern Matches - true if the whole text matches the regular expression pattern Equals - true if the whole text equals the pattern string (case-sensitive) Substring - true ... | Yes |
| Patterns to Test | A list of patterns to be tested. Each pattern is tested separately. If a pattern fails, then further patterns are not checked. There is no difference between setting up one Assertion with multiple patterns and setting up multiple Assertions with one pattern each (assuming the other options are the s... | Yes |
| Custom failure message | Lets you define the failure message that will replace the generated one | No |


### Duration Assertion

The Duration Assertion tests that each response was received within a given amount of time. Any response that takes longer than the given number of milliseconds (specified by the user) is marked as a failed response.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. |  |
| Duration in Milliseconds | The maximum number of milliseconds each response is allowed before being marked as failed. | Yes |


### Size Assertion

The Size Assertion tests that each response contains the right number of bytes in it. You can specify that the size be equal to, greater than, less than, or not equal to a given number of bytes.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. |  |
| Apply to: | This for use with samplers that can generate sub-samples, e.g. HTTP Sampler with embedded resources, Mail Reader or samples generated by the Transaction Controller. Main sample only - assertion only applies to the main sample Sub-samples only - assertion only applies to the sub-samples Main sampl... | Yes |
| Size in bytes | The number of bytes to use in testing the size of the response (or value of the JMeter variable). | Yes |
| Type of Comparison | Whether to test that the response is equal to, greater than, less than, or not equal to, the number of bytes specified. | Yes |


### XML Assertion

The XML Assertion tests that the response data consists of a formally correct XML document. It does not validate the XML based on a DTD or schema or do any further validation.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. |  |


### BeanShell Assertion

The BeanShell Assertion allows the user to perform assertion checking using a BeanShell script.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. The name is stored in the script variable Label |  |
| Reset bsh.Interpreter before each call | If this option is selected, then the interpreter will be recreated for each sample. This may be necessary for some long running scripts. For further information, see Best Practices - BeanShell scripting. | Yes |
| Parameters | Parameters to pass to the BeanShell script. The parameters are stored in the following variables: Parameters - string containg the parameters a single variable bsh.args - String array containg parameters, split on white-space | No |
| Script file | A file containg the BeanShell script to run. This overrides the script. The file name is stored in the script variable FileName | No |
| Script | The BeanShell script to run. The return value is ignored. | Yes (unless script file is provided) |


### MD5Hex Assertion

The MD5Hex Assertion allows the user to check the MD5 hash of the response data.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. |  |
| MD5 sum | 32 hex digits representing the MD5 hash (case not significant) | Yes |


### HTML Assertion

The HTML Assertion allows the user to check the HTML syntax of the response data using JTidy.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. |  |
| doctype | omit, auto, strict or loose | Yes |
| Format | HTML, XHTML or XML | Yes |
| Errors only | Only take note of errors? | Yes |
| Error threshold | Number of errors allowed before classing the response as failed | Yes |
| Warning threshold | Number of warnings allowed before classing the response as failed | Yes |
| Filename | Name of file to which report is written | No |


### XPath Assertion

The XPath Assertion tests a document for well formedness, has the option of validating against a DTD, or putting the document through JTidy and testing for an XPath. If that XPath exists, the Assertion is true. Using "/" will match any well-formed document, and is the default XPath Expression. The assertion also supports boolean expressions, such as "count(//*error)=2". See http://www.w3.org/TR/xpathhttp://www.w3.org/TR/xpath for more information XPath.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. | No |
| Use Tidy (tolerant parser) | Use Tidy, i.e. be tolerant of XML/HTML errors | Yes |
| Quiet | Sets the Tidy Quiet flag | If Tidy is selected |
| Report Errors | If a Tidy error occurs, then set the Assertion accordingly | If Tidy is selected |
| Show warnings | Sets the Tidy showWarnings option | If Tidy is selected |
| Use Namespaces | Should namespaces be honoured? (see note below on NAMESPACES) | If Tidy is not selected |
| Validate XML | Check the document against its schema. | If Tidy is not selected |
| Ignore Whitespace | Ignore Element Whitespace. | If Tidy is not selected |
| Fetch External DTDs | If selected, external DTDs are fetched. | If Tidy is not selected |
| XPath Assertion | XPath to match in the document. | Yes |
| Invert assertion(will fail if above conditions met) | True if a XPath expression is not matched or returns false | No |


### XPath2 Assertion

The XPath2 Assertion tests a document for well formedness. Using "/" will match any well-formed document, and is the default XPath2 Expression. The assertion also supports boolean expressions, such as "count(//*error)=2".

| Property | Description | Required |
|----------|-------------|----------|
| Namespaces aliases list | List of namespaces aliases you want to use to parse the document, one line per declaration. You must specify them as follow: prefix=namespace. This implementation makes it easier to use namespaces than with the old XPathExtractor version. | No |
| XPath2 Assertion | XPath to match in the document. | Yes |
| Invert assertion | Will fail if xpath expression returns true or matches, succeed otherwise | No |
| Namespace aliases list | List of namespace aliases prefix=full namespace (one per line) | No |


### XML Schema Assertion

The XML Schema Assertion allows the user to validate a response against an XML Schema.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. |  |
| File Name | Specify XML Schema File Name | Yes |


### JSR223 Assertion

The JSR223 Assertion allows JSR223 script code to be used to check the status of the previous sample.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. | No |
| Language | The JSR223 language to be used | Yes |
| Parameters | Parameters to pass to the script. The parameters are stored in the following variables: Parameters - string containg the parameters a single variable args - String array containg parameters, split on white-space | No |
| Script file | A file containg the script to run, if a relative file path is used, then it will be relative to directory referenced by "user.dir" System property | No |
| Script compilation caching | Unique String across Test Plan that JMeter will use to cache result of Script compilation if language used supports Compilable interface (Groovy is one of these, java, BeanShell and JavaScript are not) See note in JSR223 Sampler Java System property if you're using Groovy without checking ... | No |
| Script | The script to run. | Yes (unless script file is provided) |


### Compare Assertion

The Compare Assertion can be used to compare sample results within its scope. Either the contents or the elapsed time can be compared, and the contents can be filtered before comparison. The assertion comparisons can be seen in the Comparison Assertion Visualizer.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. | No |
| Compare Content | Whether or not to compare the content (response data) | Yes |
| Compare Time | If the value is ≥0, then check if the response time difference is no greater than the value. I.e. if the value is 0, then the response times must be exactly equal. | Yes |
| Comparison Filters | Filters can be used to remove strings from the content comparison. For example, if the page has a time-stamp, it might be matched with: "Time: \d\d:\d\d:\d\d" and replaced with a dummy fixed time "Time: HH:MM:SS". | No |


### SMIME Assertion

If using the Mail Reader Sampler, please ensure that you select "Store the message using MIME (raw)" otherwise the Assertion won't be able to process the message correctly.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. | No |
| Verify Signature | If selected, the assertion will verify if it is a valid signature according to the parameters defined in the Signer Certificate box. | Yes |
| Message not signed | Whether or not to expect a signature in the message | Yes |
| Signer Certificate | "No Check" means that it will not perform signature verification. "Check values" is used to verify the signature against the inputs provided. And "Certificate file" will perform the verification against a specific certificate file. | Yes |
| Message Position | The Mail sampler can retrieve multiple messages in a single sample. Use this field to specify which message will be checked. Messages are numbered from 0, so 0 means the first message. Negative numbers count from the LAST message; -1 means LAST, -2 means penultimate etc. | Yes |


### JSON Assertion

This component allows you to perform validations of JSON documents. First, it will parse the JSON and fail if the data is not JSON. Second, it will search for specified path, using syntax from Jayway JsonPath 1.2.0Jayway JsonPath 1.2.0. If the path is not found, it will fail. Third, if JSON path was found in the document, and validation against expected value was requested, it will perform validation. For the null value there is special checkbox in the GUI. Note that if the path will return array object, it will be iterated and if expected value is found, the assertion will succeed. To validat...

| Property | Description | Required |
|----------|-------------|----------|
| Assert JSON Path exists | Path to JSON element for assert. | Yes |
| Additionally assert value | Select checkbox if you want make assert with some value | No |
| Match as regular expression | Select checkbox if you want use regular expression | No |
| Expected Value | Value for assert or regular expression for match | No |
| Expect null | Select checkbox if you expect null | No |
| Invert assertion (will fail if above conditions met) | Invert assertion (will fail if above conditions met) | No |


### JSON JMESPath Assertion

This component allows you to perform assertion JSON documents content using JMESPath. First, it will parse the JSON and fail if the data is not JSON. Second, it will search for specified path, using JMESPath syntax. If the path is not found, it will fail. Third, if JMES path was found in the document, and validation against expected value was requested, it will perform this additional check. If you want to check for nullity, use the Expect null checkbox. Note that the path cannot be null as the expression JMESPath will not be compiled an error will occur. Even if you expect an e...

| Property | Description | Required |
|----------|-------------|----------|
| Assert JMESPath exists | Check that JMESPath to JSON element exists | Yes |
| Additionally assert value | Select checkbox if you check the extracted JMESPath against an expected one | No |
| Match as regular expression | Select checkbox if you want to use a regular expression for matching | No |
| Expected Value | Value to use for exact matching or regular expression if Match as regular expression is checked | No |
| Expect null | Select checkbox if you expect the value to be null | No |
| Invert assertion (will fail if above conditions met) | Invert assertion (will fail if above conditions met) | No |


## 18.6 Timers

### Constant Timer

If you want to have each thread pause for the same amount of time between requests, use this timer.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this timer that is shown in the tree. | No |
| Thread Delay | Number of milliseconds to pause. | Yes |


### Gaussian Random Timer

This timer pauses each thread request for a random amount of time, with most of the time intervals occurring near a particular value. The total delay is the sum of the Gaussian distributed value (with mean 0.0 and standard deviation 1.0) times the deviation value you specify, and the offset value. Another way to explain it, in Gaussian Random Timer, the variation around constant offset has a Gaussian curve distribution.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this timer that is shown in the tree | No |
| Deviation | Deviation in milliseconds. | Yes |
| Constant Delay Offset | Number of milliseconds to pause in addition to the random delay. | Yes |


### Uniform Random Timer

This timer pauses each thread request for a random amount of time, with each time interval having the same probability of occurring. The total delay is the sum of the random value and the offset value.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this timer that is shown in the tree. | No |
| Random Delay Maximum | Maximum random number of milliseconds to pause. | Yes |
| Constant Delay Offset | Number of milliseconds to pause in addition to the random delay. | Yes |


### Constant Throughput Timer

This timer introduces variable pauses, calculated to keep the total throughput (in terms of samples per minute) as close as possible to a given figure. Of course throughput will be lower if the server is not capable of handling it, or if other timers or time-consuming test elements prevent it.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this timer that is shown in the tree. | No |
| Target Throughput | Throughput we want the timer to try to generate. | Yes |
| Calculate Throughput based on | this thread only - each thread will try to maintain the target throughput. The overall throughput will be proportional to the number of active threads. all active threads in current thread group - the target throughput is divided amongst all the active threads in the group. Each thread will delay as... | Yes |


### Precise Throughput Timer

This timer introduces variable pauses, calculated to keep the total throughput (e.g. in terms of samples per minute) as close as possible to a given figure. The timer does not generate threads, so the resulting throughput will be lower if the server is not capable of handling it, or if other timers add too big delays, or if there's not enough threads, or time-consuming test elements prevent it.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this timer that is shown in the tree | No |
| Target throughput (in samples per 'throughput period') | Maximum number of samples you want to obtain per "throughput period", including all threads in group, from all affected samplers. | Yes |
| Throughput period (seconds) | Throughput period. For example, if "throughput" is set to 42 and "throughput period" to 21 sec, then you'll get 2 samples per second. | Yes |
| Test duration (seconds) | This used to ensure you'll get throughput*duration samples during "test duration" timeframe. | Yes |
| Number of threads in the batch (threads) | If the value exceeds 1, then multiple threads depart from the timer simultaneously. Average throughput still meets "throughput" value. | Yes |
| Delay between threads in the batch (ms) | For instance, if set to 42, and the batch size is 3, then threads will depart at x, x+42ms, x+84ms. | Yes |
| Random seed (change from 0 to random) | Note: different timers should better have different seed values. Constant seed ensures timer generates the same delays each test start. The value of "0" means the timer is truly random (non-repeatable from one execution to another).. | Yes |


### Synchronizing Timer

The purpose of the SyncTimer is to block threads until X number of threads have been blocked, and then they are all released at once. A SyncTimer can thus create large instant loads at various points of the test plan.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this timer that is shown in the tree. | No |
| Number of Simultaneous Users to Group by | Number of threads to release at once. Setting it to 0 is equivalent to setting it to Number of threads in Thread Group. | Yes |
| Timeout in milliseconds | If set to 0, Timer will wait for the number of threads to reach the value in "Number of Simultaneous Users to Group". If superior to 0, then timer will wait at max "Timeout in milliseconds" for the number of Threads. If after the timeout interval the number of users waiting is not reached, timer wil... | No |


### BeanShell Timer

The BeanShell Timer can be used to generate a delay.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. The name is stored in the script variable Label | No |
| Reset bsh.Interpreter before each call | If this option is selected, then the interpreter will be recreated for each sample. This may be necessary for some long running scripts. For further information, see Best Practices - BeanShell scripting. | Yes |
| Parameters | Parameters to pass to the BeanShell script. The parameters are stored in the following variables: Parameters - string containg the parameters a single variable bsh.args - String array containg parameters, split on white-space | No |
| Script file | A file containg the BeanShell script to run. The file name is stored in the script variable FileName The return value is used as the number of milliseconds to wait. | No |
| Script | The BeanShell script. The return value is used as the number of milliseconds to wait. | Yes (unless script file is provided) |


### JSR223 Timer

The JSR223 Timer can be used to generate a delay using a JSR223 scripting language,

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. | No |
| ScriptLanguage | The scripting language to be used. | Yes |
| Parameters | Parameters to pass to the script. The parameters are stored in the following variables: Parameters - string containg the parameters a single variable args - String array containg parameters, split on white-space | No |
| Script file | A file containg the script to run, if a relative file path is used, then it will be relative to directory referenced by "user.dir" System property The return value is converted to a long integer and used as the number of milliseconds to wait. | No |
| Script compilation caching | Unique String across Test Plan that JMeter will use to cache result of Script compilation if language used supports Compilable interface (Groovy is one of these, java, beanshell and javascript are not) See note in JSR223 Sampler Java System property if you're using Groovy without checking ... | No |
| Script | The script. The return value is used as the number of milliseconds to wait. | Yes (unless script file is provided) |


### Poisson Random Timer

This timer pauses each thread request for a random amount of time, with most of the time intervals occurring near a particular value. The total delay is the sum of the Poisson distributed value, and the offset value.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this timer that is shown in the tree | No |
| Lambda | Lambda value in milliseconds. | Yes |
| Constant Delay Offset | Number of milliseconds to pause in addition to the random delay. | Yes |


## 18.7 Pre Processors

### HTML Link Parser

This modifier parses HTML response from the server and extracts links and forms. A URL test sample that passes through this modifier will be examined to see if it "matches" any of the links or forms extracted from the immediately previous response. It would then replace the values in the URL test sample with appropriate values from the matching link or form. Perl-type regular expressions are used to find matches.


### HTTP URL Re-writing Modifier

This modifier works similarly to the HTML Link Parser, except it has a specific purpose for which it is easier to use than the HTML Link Parser, and more efficient. For web applications that use URL Re-writing to store session ids instead of cookies, this element can be attached at the ThreadGroup level, much like the HTTP Cookie Manager. Simply give it the name of the session id parameter, and it will find it on the page and add the argument to every request of that ThreadGroup.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name given to this element in the test tree. | No |
| Session Argument Name | The name of the parameter to grab from previous response. This modifier will find the parameter anywhere it exists on the page, and grab the value assigned to it, whether it's in an HREF or a form. | Yes |
| Path Extension | Some web apps rewrite URLs by appending a semi-colon plus the session id parameter. Check this box if that is so. | No |
| Do not use equals in path extension | Some web apps rewrite URLs without using an "=" sign between the parameter name and value (such as Intershop Enfinity). | No |
| Do not use questionmark in path extension | Prevents the query string to end up in the path extension (such as Intershop Enfinity). | No |
| Cache Session Id? | Should the value of the session Id be saved for later use when the session Id is not present? | Yes |
| URL Encode | URL Encode value when writing parameter | No |


### User Parameters

Allows the user to specify values for User Variables specific to individual threads.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. |  |
| Update Once Per Iteration | A flag to indicate whether the User Parameters element should update its variables only once per iteration. if you embed functions into the UP, then you may need greater control over how often the values of the variables are updated. Keep this box checked to ensure the values are updated each time t... | Yes |


### BeanShell PreProcessor

The BeanShell PreProcessor allows arbitrary code to be applied before taking a sample.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. The name is stored in the script variable Label | No |
| Reset bsh.Interpreter before each call | If this option is selected, then the interpreter will be recreated for each sample. This may be necessary for some long running scripts. For further information, see Best Practices - BeanShell scripting. | Yes |
| Parameters | Parameters to pass to the BeanShell script. The parameters are stored in the following variables: Parameters - string containg the parameters a single variable bsh.args - String array containg parameters, split on white-space | No |
| Script file | A file containg the BeanShell script to run. The file name is stored in the script variable FileName | No |
| Script | The BeanShell script. The return value is ignored. | Yes (unless script file is provided) |


### JSR223 PreProcessor

The JSR223 PreProcessor allows JSR223 script code to be applied before taking a sample.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. | No |
| Language | The JSR223 language to be used | Yes |
| Parameters | Parameters to pass to the script. The parameters are stored in the following variables: Parameters - string containg the parameters a single variable args - String array containg parameters, split on white-space | No |
| Script file | A file containg the script to run, if a relative file path is used, then it will be relative to directory referenced by "user.dir" System property | No |
| Script compilation caching | Unique String across Test Plan that JMeter will use to cache result of Script compilation if language used supports Compilable interface (Groovy is one of these, java, beanshell and javascript are not) See note in JSR223 Sampler Java System property if you're using Groovy without checking ... | No |
| Script | The script to run. | Yes (unless script file is provided) |


### JDBC PreProcessor

The JDBC PreProcessor enables you to run some SQL statement just before a sample runs. This can be useful if your JDBC Sample requires some data to be in DataBase and you cannot compute this in a setup Thread group. For details, see JDBC Request.


### RegEx User Parameters

Allows to specify dynamic values for HTTP parameters extracted from another HTTP Request using regular expressions. RegEx User Parameters are specific to individual threads.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. |  |
| Regular Expression Reference Name | Name of a reference to a regular expression | Yes |
| Parameter names regexp group number | Group number of regular expression used to extract parameter names | Yes |
| Parameter values regex group number | Group number of regular expression used to extract parameter values | Yes |


### Sample Timeout

This Pre-Processor schedules a timer task to interrupt a sample if it takes too long to complete. The timeout is ignored if it is zero or negative. For this to work, the sampler must implement Interruptible. The following samplers are known to do so: AJP, BeanShell, FTP, HTTP, Soap, AccessLog, MailReader, JMS Subscriber, TCPSampler, TestAction, JavaSampler

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this timer that is shown in the tree. | No |
| Sample Timeout | If the sample takes longer to complete, it will be interrupted. | Yes |


## 18.8 Post-Processors

### Regular Expression Extractor

Allows the user to extract values from a server response using a Perl-type regular expression. As a post-processor, this element will execute after each Sample request in its scope, applying the regular expression, extracting the requested values, generate the template string, and store the result into the given variable name.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. |  |
| Apply to: | This for use with samplers that can generate sub-samples, e.g. HTTP Sampler with embedded resources, Mail Reader or samples generated by the Transaction Controller. Main sample only - only applies to the main sample Sub-samples only - only applies to the sub-samples Main sample and sub-samples - ... | Yes |
| Field to check | The following fields can be checked: Body - the body of the response, e.g. the content of a web-page (excluding headers) Body (unescaped) - the body of the response, with all Html escape codes replaced. Note that Html escapes are processed without regard to context, so some incorrect substitutions m... | Yes |
| Name of created variable | The name of the JMeter variable in which to store the result. Also note that each group is stored as [refname]_g#, where [refname] is the string you entered as the reference name, and # is the group number, where group 0 is the entire match, group 1 is the match from the first set of parenthes, et... | Yes |
| Regular Expression | The regular expression used to parse the response data. This must contain at least one set of parenthes "()" to capture a portion of the string, unless using the group $0$. Do not enclose the expression in / / - unless of course you want to match these characters as well. | Yes |
| Template | The template used to create a string from the matches found. This an arbitrary string with special elements to refer to groups within the regular expression. The syntax to refer to a group is: '$1$' to refer to group 1, '$2$' to refer to group 2, etc. $0$ refers to whatever the entire expression ... | Yes |
| Match No. (0 for Random) | Indicates which match to use. The regular expression may match multiple times. Use a value of zero to indicate JMeter should choose a match at random. A positive number N means to select the nth match. Negative numbers are used in conjunction with the ForEach Controller - see below... | Yes |
| Default Value | If the regular expression does not match, then the reference variable will be set to the default value. This particularly useful for debugging tests. If no default is provided, then it is difficult to tell whether the regular expression did not match, or the RE element was not processed or maybe ... | No, but recommended |
| Use empty default value | If the checkbox is checked and Default Value is empty, then JMeter will set the variable to empty string instead of not setting it. Thus when you will for example use ${var} (if Reference Name is var) in your Test Plan, if the extracted value is not found then ${var} will be equal to empty string in... | No |


### CSS Selector Extractor(was: CSS/JQuery Extractor)

Allows the user to extract values from a server HTML response using a CSS Selector syntax. As a post-processor, this element will execute after each Sample request in its scope, applying the CSS/JQuery expression, extracting the requested nodes, extracting the node as text or attribute value and store the result into the given variable name.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. |  |
| Apply to: | This for use with samplers that can generate sub-samples, e.g. HTTP Sampler with embedded resources, Mail Reader or samples generated by the Transaction Controller. Main sample only - only applies to the main sample Sub-samples only - only applies to the sub-samples Main sample and sub-samples - ... | Yes |
| CSS Selector Implementation | 2 Implementations for CSS/JQuery based syntax are supported: JSoup Jodd-Lagarto (CSSelly) If selector is set to empty, default implementation(JSoup) will be used. | False |
| Name of created variable | The name of the JMeter variable in which to store the result. | Yes |
| CSS/JQuery expression | The CSS/JQuery selector used to select nodes from the response data. Selector, selectors combination and pseudo-selectors are supported, examples: E[foo] - an E element with a "foo" attribute ancestor child - child elements that descend from ancestor, e.g. .body p finds p elements anywhere under a b... | Yes |
| Attribute | Name of attribute (as per HTML syntax) to extract from nodes that matched the selector. If empty, then the combined text of this element and all its children will be returned. This the equivalent Element#attr(name)Element#attr(name) function for JSoup if an attribute is set. CSS Extractor with at... | false |
| Match No. (0 for Random) | Indicates which match to use. The CSS/JQuery selector may match multiple times. Use a value of zero to indicate JMeter should choose a match at random. A positive number N means to select the nth match. Negative numbers are used in conjunction with the ForEach Controller - see belo... | Yes |
| Default Value | If the expression does not match, then the reference variable will be set to the default value. This particularly useful for debugging tests. If no default is provided, then it is difficult to tell whether the expression did not match, or the CSS/JQuery element was not processed or maybe the wron... | No, but recommended |
| Use empty default value | If the checkbox is checked and Default Value is empty, then JMeter will set the variable to empty string instead of not setting it. Thus when you will for example use ${var} (if Reference Name is var) in your Test Plan, if the extracted value is not found then ${var} will be equal to empty string in... | No |


### XPath2 Extractor

This test element allows the user to extract value(s) from structured response - XML or (X)HTML - using XPath2 query language.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. | No |
| Apply to: | This for use with samplers that can generate sub-samples, e.g. HTTP Sampler with embedded resources, Mail Reader or samples generated by the Transaction Controller. Main sample only - only applies to the main sample Sub-samples only - only applies to the sub-samples Main sample and sub-samples - ... | Yes |
| Return entire XPath fragment instead of text content? | If selected, the fragment will be returned rather than the text content. For example //title would return "<title>Apache JMeter</title>" rather than "Apache JMeter". In this case, //title/text() would return "Apache JMeter". | Yes |
| Name of created variable | The name of the JMeter variable in which to store the result. | Yes |
| XPath Query | Element query in XPath 2.0 language. Can return more than one match. | Yes |
| Match No. (0 for Random) | If the XPath query leads to many results, you can choose which one(s) to extract as Variables: 0: means random (default value) -1 means extract all results, they will be named as *<variable name>*<variable name>_N (where N goes from 1 to Number of results) X: means extract the Xth result. If th... | No |
| Default Value | Default value returned when no match found. It is also returned if the node has no value and the fragment option is not selected. | yes |
| Namespaces aliases list | List of namespaces aliases you want to use to parse the document, one line per declaration. You must specify them as follow: prefix=namespace. This implementation makes it easier to use namespaces than with the old XPathExtractor version. | No |


### XPath Extractor

This test element allows the user to extract value(s) from structured response - XML or (X)HTML - using XPath query language.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. | No |
| Apply to: | This for use with samplers that can generate sub-samples, e.g. HTTP Sampler with embedded resources, Mail Reader or samples generated by the Transaction Controller. Main sample only - only applies to the main sample Sub-samples only - only applies to the sub-samples Main sample and sub-samples - ... | Yes |
| Use Tidy (tolerant parser) | If checked use Tidy to parse HTML response into XHTML. "Use Tidy" should be checked on for HTML response. Such response is converted to valid XHTML (XML compatible HTML) using Tidy "Use Tidy" should be unchecked for both XHTML or XML response (for example RSS) For HTML, CSS Selector Extractor is the... | Yes |
| Quiet | Sets the Tidy Quiet flag | If Tidy is selected |
| Report Errors | If a Tidy error occurs, then set the Assertion accordingly | If Tidy is selected |
| Show warnings | Sets the Tidy showWarnings option | If Tidy is selected |
| Use Namespaces | If checked, then the XML parser will use namespace resolution.(see note below on NAMESPACES) Note that currently only namespaces declared on the root element will be recognised. See below for user-definition of additional workspace names. | If Tidy is not selected |
| Validate XML | Check the document against its schema. | If Tidy is not selected |
| Ignore Whitespace | Ignore Element Whitespace. | If Tidy is not selected |
| Fetch External DTDs | If selected, external DTDs are fetched. | If Tidy is not selected |
| Return entire XPath fragment instead of text content? | If selected, the fragment will be returned rather than the text content. For example //title would return "<title>Apache JMeter</title>" rather than "Apache JMeter". In this case, //title/text() would return "Apache JMeter". | Yes |
| Name of created variable | The name of the JMeter variable in which to store the result. | Yes |
| XPath Query | Element query in XPath language. Can return more than one match. | Yes |
| Match No. (0 for Random) | If the XPath query leads to many results, you can choose which one(s) to extract as Variables: 0: means random -1 means extract all results (default value), they will be named as *<variable name>*<variable name>_N (where N goes from 1 to Number of results) X: means extract the Xth result. If th... | No |
| Default Value | Default value returned when no match found. It is also returned if the node has no value and the fragment option is not selected. |  |


### JSON JMESPath Extractor

This test element allows the user to extract value(s) from JSON response using JMESPath query language.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. | No |
| Apply to: | This for use with samplers that can generate sub-samples, e.g. HTTP Sampler with embedded resources, Mail Reader or samples generated by the Transaction Controller. Main sample only - only applies to the main sample Sub-samples only - only applies to the sub-samples Main sample and sub-samples - ... | Yes |
| Name of created variable | The name of the JMeter variable in which to store the result. | Yes |
| JMESPath expressions | Element query in JMESPath query language. Can return the matched result. | Yes |
| Match No. (0 for Random) | If the JMESPath query leads to many results, you can choose which one(s) to extract as Variables: 0: means random -1 means extract all results (default value), they will be named as *<variable name>*<variable name>_N (where N goes from 1 to Number of results) X: means extract the Xth result. If this... | No |
| Default Value | Default value returned when no match found. It is also returned if the node has no value and the fragment option is not selected. |  |


### Result Status Action Handler

This test element allows the user to stop the thread or the whole test if the relevant sampler failed.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. |  |
| Action to be taken after a Sampler error | Determines what happens if a sampler error occurs, either because the sample itself failed or an assertion failed. The possible choices are: Continue - ignore the error and continue with the test Start next thread loop - does not execute samplers following the sampler in error for the current iterat... | No |


### BeanShell PostProcessor

The BeanShell PreProcessor allows arbitrary code to be applied after taking a sample.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. The name is stored in the script variable Label | No |
| Reset bsh.Interpreter before each call | If this option is selected, then the interpreter will be recreated for each sample. This may be necessary for some long running scripts. For further information, see Best Practices - BeanShell scripting. | Yes |
| Parameters | Parameters to pass to the BeanShell script. The parameters are stored in the following variables: Parameters - string containg the parameters a single variable bsh.args - String array containg parameters, split on white-space | No |
| Script file | A file containg the BeanShell script to run. The file name is stored in the script variable FileName | No |
| Script | The BeanShell script. The return value is ignored. | Yes (unless script file is provided) |


### JSR223 PostProcessor

The JSR223 PostProcessor allows JSR223 script code to be applied after taking a sample.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. | No |
| Language | The JSR223 language to be used | Yes |
| Parameters | Parameters to pass to the script. The parameters are stored in the following variables: Parameters - string containg the parameters a single variable args - String array containg parameters, split on white-space | No |
| Script file | A file containg the script to run, if a relative file path is used, then it will be relative to directory referenced by "user.dir" System property | No |
| Script compilation caching | Unique String across Test Plan that JMeter will use to cache result of Script compilation if language used supports Compilable interface (Groovy is one of these, java, beanshell and javascript are not) See note in JSR223 Sampler Java System property if you're using Groovy without checking ... | No |
| Script | The script to run. | Yes (unless script file is provided) |


### JDBC PostProcessor

The JDBC PostProcessor enables you to run some SQL statement just after a sample has run. This can be useful if your JDBC Sample changes some data and you want to reset state to what it was before the JDBC sample run.


### JSON Extractor

The JSON PostProcessor enables you extract data from JSON responses using JSON-PATH syntax. This post processor is very similar to Regular expression extractor. It must be placed as a child of HTTP Sampler or any other sampler that has responses. It will allow you to extract in a very easy way text content, see JSON Path syntax.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. | No |
| Apply to: | This for use with samplers that can generate sub-samples, e.g. HTTP Sampler with embedded resources, Mail Reader or samples generated by the Transaction Controller. Main sample only applies to the main sample Sub-samples only applies to the sub-samples Main sample and sub-samples applie... | Yes |
| Names of created variables | Semicolon separated names of variables that will contain the results of JSON-PATH expressions (must match number of JSON-PATH expressions) | Yes |
| JSON Path Expressions | Semicolon separated JSON-PATH expressions (must match number of variables) | Yes |
| Default Values | Semicolon separated default values if JSON-PATH expressions do not return any result(must match number of variables) | No |
| Match Numbers | For each JSON Path Expression, if the JSON Path query leads to many results, you can choose which one(s) to extract as Variables: 0: means random (Default Value) -1 means extract all results, they will be named as *<variable name>*<variable name>_N (where N goes from 1 to Number of results) X: means... | No |
| Compute concatenation var | If many results are found, plugin will concatenate them using ‘,’ separator and store it in a var named *<variable name>*<variable name>_ALL | No |


### Boundary Extractor

Allows the user to extract values from a server response using left and right boundaries. As a post-processor, this element will execute after each Sample request in its scope, testing the boundaries, extracting the requested values, generate the template string, and store the result into the given variable name.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. |  |
| Apply to: | This for use with samplers that can generate sub-samples, e.g. HTTP Sampler with embedded resources, Mail Reader or samples generated by the Transaction Controller. Main sample only - only applies to the main sample Sub-samples only - only applies to the sub-samples Main sample and sub-samples - ... | Yes |
| Field to check | The following fields can be checked: Body - the body of the response, e.g. the content of a web-page (excluding headers) Body (unescaped) - the body of the response, with all Html escape codes replaced. Note that Html escapes are processed without regard to context, so some incorrect substitutions m... | Yes |
| Name of created variable | The name of the JMeter variable in which to store the result. Also note that each group is stored as [refname]_g#, where [refname] is the string you entered as the reference name, and # is the group number, where group 0 is the entire match, group 1 is the match from the first set of parenthes, et... | Yes |
| Left Boundary | Left boundary of value to find | No |
| Right Boundary | Right boundary of value to find | No |
| Match No. (0 for Random) | Indicates which match to use. The boundaries may match multiple times. Use a value of zero to indicate JMeter should choose a match at random. A positive number N means to select the nth match. Negative numbers are used in conjunction with the ForEach Controller - see below. | Yes |
| Default Value | If the boundaries do not match, then the reference variable will be set to the default value. This particularly useful for debugging tests. If no default is provided, then it is difficult to tell whether the boundaries did not match, or maybe the wrong variable is being used. However, if you have... | No, but recommended |


## 18.9 Miscellaneous Features

### Test Plan

The Test Plan is where the overall settings for a test are specified.


### Open Model Thread Group

Open Model Thread Group defines a pool of users that will execute a particular test case against the server. The users are generated according to the schedule.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this thread group that is shown in the tree | No |
| Schedule | The expression that configures schedule. For example: rate(5/sec) random_arrivals(1 min) pause(5 sec) | Yes |
| Random Seed (change from 0 to random) | Note: different thread groups should better have different seed values. Constant seed ensures thread group generates the same delays each test start. The value of "0" means the schedule is truly random (non-repeatable from one execution to another).. | No |


### Thread Group

A Thread Group defines a pool of users that will execute a particular test case against your server. In the Thread Group GUI, you can control the number of users simulated (number of threads), the ramp up time (how long it takes to start all the threads), the number of times to perform the test, and optionally, a start and stop time for the test.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. |  |
| Action to be taken after a Sampler error | Determines what happens if a sampler error occurs, either because the sample itself failed or an assertion failed. The possible choices are: Continue - ignore the error and continue with the test Start Next Thread Loop - ignore the error, start next loop and continue with the test Stop Thread - curr... | No |
| Number of Threads | Number of users to simulate. | Yes |
| Ramp-up Period | How long JMeter should take to get all the threads started. If there are 10 threads and a ramp-up time of 100 seconds, then each thread will begin 10 seconds after the previous thread started, for a total time of 100 seconds to get the test fully up to speed. The first thread will always start direc... | Yes |
| Same user on each iteration | If selected, cookie and cache data from the first sampler response are used in subsequent requests (requires a global Cookie and Cache Manager respectively). If not selected, cookie and cache data from the first sampler response are not used in subsequent requests. If not selected, a new connection ... | Yes |
| Loop Count | Number of times to perform the test case. Alternatively, "infinite" can be selected causing the test to run until manually stopped or end of the thread lifetime is reached. | Yes, unless Infinite is selected |
| Same user on each iteration | If selected, cookie and cache data from the first sampler response are used in subsequent requests (requires a global Cookie and Cache Manager respectively). If not selected, cookie and cache data from the first sampler response are not used in subsequent requests. If not selected, a new connection ... | Yes |
| Delay Thread creation until need | If selected, threads are created only when the appropriate proportion of the ramp-up time has elapsed. This most appropriate for tests with a ramp-up time that is significantly longer than the time to execute a single thread. I.e. where earlier threads finish before later ones start. If not selec... | Yes |
| Specify Thread lifetime | If selected, confines Thread operation time to the given bounds | Yes |
| Duration (seconds) | If the scheduler checkbox is selected, one can choose a relative end time. JMeter will use this to calculate the End Time. | No |
| Startup delay (seconds) | If the scheduler checkbox is selected, one can choose a relative startup delay. JMeter will use this to calculate the Start Time. | No |


### WorkBench


### SSL Manager


### HTTP(S) Test Script Recorder(was: HTTP Proxy Server)

The HTTP(S) Test Script Recorder allows JMeter to intercept and record your actions while you browse your web application with your normal browser. JMeter will create test sample objects and store them directly into your test plan as you go (so you can view samples interactively while you make them). Ensure you read this wiki page to setup correctly JMeter.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. | No |
| Port | The port that the HTTP(S) Test Script Recorder listens to. 8888 is the default, but you can change it. | Yes |
| HTTPS Domains | List of domain (or host) names for HTTPS. Use this to pre-generate certificates for all servers you wish to record. For example, *.example.com,*.subdomain.example.com Note that wildcard domains only apply to one level, i.e. abc.subdomain.example.com matches *.subdomain.example.com but not *.example.... | No |
| Target Controller | The controller where the proxy will store the generated samples. By default, it will look for a Recording Controller and store them there wherever it is. | Yes |
| Grouping | Whether to group samplers for requests from a single "click" (requests received without significant time separation), and how to represent that grouping in the recording: Do not group samplers - store all recorded samplers sequentially, without any grouping. Add separators between groups - add a con... | Yes |
| Capture HTTP Headers | Should headers be added to the plan? If specified, a Header Manager will be added to each HTTP Sampler. The Proxy server always removes Cookie and Authorization headers from the generated Header Managers. By default it also removes If-Modified-Since and If-None-Match headers. These are used to deter... | Yes |
| Add Assertions | Add a blank assertion to each sampler? | Yes |
| Regex Matching | Use Regex Matching when replacing variables? If checked replacement will use word boundaries, i.e. it will only replace word matching values of variable, not part of a word. A word boundary follows Perl5 definition and is equivalent to \b. More information below in the paragraph about "User Defined ... | Yes |
| Prefix/Transaction name | Add a prefix to sampler name during recording (Prefix mode). Or replace sampler name by user chosen name (Transaction name) | No |
| Naming scheme | Select the naming scheme for sampler names during recording. Default is Transaction name | No |
| Naming format | If Use format string is selected as naming scheme, a freestyle format can be given. Placeholders for the transaction name, scheme, host, port, path and counter can be given by #{name}, #{scheme}, #{host}, #{port}, #{path}, #{url} and #{counter}. A simple format could be "#{name}-#{counter}", which w... | No |
| Counter start value | Can be used to reset the counter to a given value. Note, that the next sample will first increment and then use the value. If the first sampler should start with 1, reset the counter to 0. | No |
| Create new transaction after request (ms) | Inactivity time between two requests need to consider them in two separate groups. | No |
| Type | Which type of sampler to generate (the HTTPClient default or Java) | Yes |
| Redirect Automatically | Set Redirect Automatically in the generated samplers? | Yes |
| Follow Redirects | Set Follow Redirects in the generated samplers? Note: see "Recording and redirects" section below for important information. | Yes |
| Use Keep-Alive | Set Use Keep-Alive in the generated samplers? | Yes |
| Retrieve all Embedded Resources | Set Retrieve all Embedded Resources in the generated samplers? | Yes |
| Content Type filter | Filter the requests based on the content-type - e.g. "text/html [;charset=utf-8 ]". The fields are regular expressions which are checked to see if they are contained in the content-type. [Does not have to match the entire field]. The include filter is checked first, then the exclude filter. Samples ... | No |
| Patterns to Include | Regular expressions that are matched against the full URL that is sampled. Allows filtering of requests that are recorded. All requests pass through, but only those that meet the requirements of the Include/Exclude fields are *recorded*recorded. If both Include and Exclude are left empty, then every... | No |
| Patterns to Exclude | Regular expressions that are matched against the URL that is sampled. Any requests that match one or more Exclude pattern are *not*not recorded . | No |
| Notify Child Listeners of filtered samplers | Notify Child Listeners of filtered samplers Any response that match one or more Exclude pattern is *not*not delivered to Child Listeners (View Results Tree) . | No |
| Start Button | Start the proxy server. JMeter writes the following message to the console once the proxy server has started up and is ready to take requests: "Proxy up and running!". | N/A |
| Stop Button | Stop the proxy server. | N/A |
| Restart Button | Stops and restarts the proxy server. This useful when you change/add/delete an include/exclude filter expression. | N/A |


### HTTP Mirror Server

The HTTP Mirror Server is a very simple HTTP server - it simply mirrors the data sent to it. This useful for checking the content of HTTP requests.

| Property | Description | Required |
|----------|-------------|----------|
| Port | Port on which Mirror server listens, defaults to 8081. | Yes |
| Max Number of threads | If set to a value > 0, number of threads serving requests will be limited to the configured number, if set to a value ≤ 0 a new thread will be created to serve each incoming request. Defaults to 0 | No |
| Max Que size | Size of que used for holding tasks before they are executed by Thread Pool, when Thread pool is exceed, incoming requests will be held in this que and discarded when this que is full. This parameter is only used if Max Number of Threads is greater than 0. Defaults to 25 | No |


### Property Display

The Property Display shows the values of System or JMeter properties. Values can be changed by entering new text in the Value column.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. | No |


### Debug Sampler

The Debug Sampler generates a sample containg the values of all JMeter variables and/or properties.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. | No |
| JMeter Properties | Include JMeter properties? | Yes |
| JMeter Variables | Include JMeter variables? | Yes |
| System Properties | Include System properties? | Yes |


### Debug PostProcessor

The Debug PostProcessor creates a subSample with the details of the previous Sampler properties, JMeter variables, properties and/or System Properties.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. | No |
| JMeter Properties | Whether to show JMeter properties (default false). | Yes |
| JMeter Variables | Whether to show JMeter variables (default false). | Yes |
| Sampler Properties | Whether to show Sampler properties (default true). | Yes |
| System Properties | Whether to show System properties (default false). | Yes |


### Test Fragment

The Test Fragment is used in conjunction with the Include Controller and Module Controller.

| Property | Description | Required |
|----------|-------------|----------|
| Name | Descriptive name for this element that is shown in the tree. | Yes |


### setUp Thread Group

A special type of ThreadGroup that can be utilized to perform Pre-Test Actions. The behavior of these threads is exactly like a normal Thread Group element. The difference is that these type of threads execute before the test proceeds to the executing of regular Thread Groups.


### tearDown Thread Group

A special type of ThreadGroup that can be utilized to perform Post-Test Actions. The behavior of these threads is exactly like a normal Thread Group element. The difference is that these type of threads execute after the test has finished executing its regular Thread Groups.

