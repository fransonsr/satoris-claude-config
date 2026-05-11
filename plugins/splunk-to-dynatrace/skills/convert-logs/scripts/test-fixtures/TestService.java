package org.familysearch.test;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class TestService {

    private static final Logger LOGGER = LoggerFactory.getLogger(TestService.class);

    public void processRecord(String personId, String ordinanceType) {
        LOGGER.atInfo().addKeyValue("person.id", personId).addKeyValue("ordinance.type", ordinanceType).addKeyValue("event.name", "person.ordinance.processing").log("Processing person ordinance");
    }

    public void handleError(String recordId, Exception error) {
        LOGGER.atError().addKeyValue("record.id", recordId).setCause(error).log("Failed to process record");
    }
}
