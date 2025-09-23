import os, jnius_config

class VnCoreNLP:
    def __init__(self, save_dir="models/vncorenlp", annotators=["wseg"], max_heap_size="-Xmx2g"):
        if save_dir.endswith("/"):
            save_dir = save_dir[:-1]

        jar_path = os.path.join(save_dir, "VnCoreNLP-1.2.jar")
        if not os.path.exists(jar_path):
            raise FileNotFoundError(f"Không tìm thấy file jar: {jar_path}")

        # cấu hình JVM
        jnius_config.add_options(max_heap_size)
        jnius_config.set_classpath(jar_path)

        from jnius import autoclass
        self.String = autoclass("java.lang.String")
        self.Annotation = autoclass("vn.pipeline.Annotation")
        self.CoreNLP = autoclass("vn.pipeline.VnCoreNLP")

        if "wseg" not in annotators:
            annotators.append("wseg")

        self.model = self.CoreNLP(annotators)

    def word_segment(self, text: str):
        ann = self.Annotation(self.String(text))
        self.model.annotate(ann)
        sentences = ann.toString().split("\n\n")[:-1]
        result = []
        for sent in sentences:
            words = [line.split("\t")[1] for line in sent.split("\n")]
            result.extend(words)
        return result
