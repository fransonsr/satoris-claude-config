import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import java.util.Objects;

/**
 * Test class with Java 16+ features.
 * Validates that Spoon transformer can parse and transform modern Java syntax.
 */
public class Java16Features {
    private static final Logger LOGGER = LoggerFactory.getLogger(Java16Features.class);

    public void processRecord(Object o) {
        // Java 16 pattern matching in instanceof
        if (o instanceof NameValuePair nameValuePair &&
            Objects.equals(nameValuePair.getName(), "test")) {

            // Traditional logging with pattern matching variable
            LOGGER.info("Processing pair with value {}", nameValuePair.getValue());
        }
    }

    // Java 16 record
    public record NameValuePair(String name, String value) {
    }
}
