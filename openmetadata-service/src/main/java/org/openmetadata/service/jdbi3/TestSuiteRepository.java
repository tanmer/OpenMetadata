package org.openmetadata.service.jdbi3;

import static org.openmetadata.service.Entity.TEST_CASE;
import static org.openmetadata.service.Entity.TEST_SUITE;

import java.io.IOException;
import java.util.List;
import org.openmetadata.schema.tests.TestSuite;
import org.openmetadata.schema.type.EntityReference;
import org.openmetadata.schema.type.Relationship;
import org.openmetadata.service.Entity;
import org.openmetadata.service.resources.dqtests.TestSuiteResource;
import org.openmetadata.service.util.EntityUtil;

public class TestSuiteRepository extends EntityRepository<TestSuite> {
  private static final String UPDATE_FIELDS = "owner,tests";
  private static final String PATCH_FIELDS = "owner,tests";

  public TestSuiteRepository(CollectionDAO dao) {
    super(
        TestSuiteResource.COLLECTION_PATH,
        TEST_SUITE,
        TestSuite.class,
        dao.testSuiteDAO(),
        dao,
        PATCH_FIELDS,
        UPDATE_FIELDS);
  }

  @Override
  public TestSuite setFields(TestSuite entity, EntityUtil.Fields fields) throws IOException {
    entity.setOwner(fields.contains("owner") ? getOwner(entity) : null);
    entity.setPipeline(fields.contains("pipelines") ? getIngestionPipeline(entity) : null);
    entity.setTests(fields.contains("tests") ? getTestCases(entity) : null);
    return entity;
  }

  @Override
  public void prepare(TestSuite entity) throws IOException {
    setFullyQualifiedName(entity);
  }

  private List<EntityReference> getTestCases(TestSuite entity) throws IOException {
    List<CollectionDAO.EntityRelationshipRecord> testCases =
        findTo(entity.getId(), TEST_SUITE, Relationship.CONTAINS, TEST_CASE);
    return EntityUtil.getEntityReferences(testCases);
  }

  @Override
  public void storeEntity(TestSuite entity, boolean update) throws IOException {
    EntityReference owner = entity.getOwner();
    // Don't store owner, database, href and tags as JSON. Build it on the fly based on relationships
    entity.withOwner(null).withHref(null);
    store(entity.getId(), entity, update);

    // Restore the relationships
    entity.withOwner(owner);
  }

  @Override
  public void storeRelationships(TestSuite entity) {
    storeOwner(entity, entity.getOwner());
  }

  private EntityReference getIngestionPipeline(TestSuite testSuite) throws IOException {
    return getToEntityRef(testSuite.getId(), Relationship.CONTAINS, Entity.INGESTION_PIPELINE, false);
  }

  public class TestSuiteUpdater extends EntityUpdater {
    public TestSuiteUpdater(TestSuite original, TestSuite updated, Operation operation) {
      super(original, updated, operation);
    }

    @Override
    public void entitySpecificUpdate() throws IOException {
      recordChange("tests", original.getTests(), updated.getTests());
    }
  }
}
